from __future__ import annotations

import re
import unicodedata
from collections import OrderedDict
from typing import Any

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.models import ChecklistItem, Chunk, Document, Edital
from app.services.ai import AIProvider

CHECKLIST_STATUSES = {"pendente", "em_andamento", "concluido", "nao_aplicavel"}


def _normalize(value: str) -> str:
    normalized = unicodedata.normalize("NFKD", value.casefold())
    return "".join(char for char in normalized if not unicodedata.combining(char))


def _clean_sentence(value: str, limit: int = 420) -> str:
    text = " ".join(value.split()).strip(" -:;\t")
    return text[:limit]


def _source_label(document_title: str, page_number: int | None) -> str:
    return f"{document_title} - p. {page_number}" if page_number else f"{document_title} - metadados"


def _context_rows(database: Session, edital_id: str) -> list[tuple[Chunk, Document]]:
    statement = (
        select(Chunk, Document)
        .join(Document, Chunk.document_id == Document.id)
        .where(Chunk.edital_id == edital_id)
        .order_by(Document.created_at.asc(), Chunk.page_number.asc().nullsfirst(), Chunk.chunk_index.asc())
    )
    return list(database.execute(statement).all())


def _default_items(edital: Edital) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = [
        {
            "category": "Prazos",
            "title": "Confirmar data e horário limite da proposta",
            "description": "Validar o encerramento, o fuso e o canal oficial de envio antes de iniciar a preparação.",
            "required": True,
            "source_reference": "Metadados do edital",
        },
        {
            "category": "Procedimentos",
            "title": "Validar condições de participação e impedimentos",
            "description": "Confirmar enquadramento, vedações, consórcios, subcontratação e demais condições de participação.",
            "required": True,
            "source_reference": "Análise geral do edital",
        },
        {
            "category": "Proposta",
            "title": "Preparar proposta comercial e planilhas exigidas",
            "description": "Conferir formato, validade, assinatura, tributos, preços e anexos da proposta.",
            "required": True,
            "source_reference": "Análise geral do edital",
        },
        {
            "category": "Habilitação",
            "title": "Reunir e validar documentos de habilitação",
            "description": "Verificar validade, assinatura, autenticação e compatibilidade dos documentos exigidos.",
            "required": True,
            "source_reference": "Análise geral do edital",
        },
    ]
    if edital.proposal_end:
        items[0]["description"] = (
            "Confirmar no portal oficial o encerramento informado para "
            f"{edital.proposal_end.strftime('%d/%m/%Y às %H:%M')} e antecipar a conferência final."
        )
    return items


RULES: tuple[tuple[str, tuple[str, ...], str, str], ...] = (
    (
        "Habilitação jurídica",
        ("contrato social", "estatuto social", "ato constitutivo", "registro comercial", "junta comercial"),
        "Apresentar documentação de habilitação jurídica",
        "Separar o ato constitutivo e comprovações de representação conforme a exigência localizada.",
    ),
    (
        "Regularidade fiscal e trabalhista",
        ("certidao negativa", "certidao positiva com efeitos", "fgts", "cndt", "fazenda nacional", "regularidade fiscal"),
        "Conferir certidões fiscais e trabalhistas",
        "Emitir as certidões exigidas e validar sua vigência na data da sessão.",
    ),
    (
        "Econômico-financeira",
        ("balanco patrimonial", "balanço patrimonial", "indices contabeis", "índices contábeis", "patrimonio liquido", "patrimônio líquido", "capital social"),
        "Preparar qualificação econômico-financeira",
        "Conferir balanço, índices, demonstrações e limites econômicos indicados no edital.",
    ),
    (
        "Qualificação técnica",
        ("atestado de capacidade", "capacidade tecnica", "capacidade técnica", "registro no conselho", "acervo tecnico", "acervo técnico"),
        "Reunir comprovação de capacidade técnica",
        "Selecionar atestados e registros compatíveis com o objeto e os quantitativos exigidos.",
    ),
    (
        "Declarações",
        ("declaracao", "declaração", "modelo de declaracao", "modelo de declaração"),
        "Preparar declarações obrigatórias",
        "Identificar todos os modelos e declarações exigidos, preencher em papel timbrado e providenciar assinatura.",
    ),
    (
        "Garantias/Amostras",
        ("garantia da proposta", "garantia contratual", "caucao", "caução"),
        "Providenciar garantia exigida",
        "Confirmar modalidade, percentual, beneficiário e prazo para apresentação da garantia.",
    ),
    (
        "Garantias/Amostras",
        ("amostra", "prova de conceito", "demonstracao tecnica", "demonstração técnica"),
        "Planejar amostra ou prova de conceito",
        "Validar critérios, prazo, local e responsável pela entrega ou apresentação.",
    ),
    (
        "Procedimentos",
        ("visita tecnica", "visita técnica", "vistoria"),
        "Avaliar visita técnica ou declaração de conhecimento",
        "Confirmar obrigatoriedade, agendamento, credenciamento e documento substitutivo quando permitido.",
    ),
    (
        "Procedimentos",
        ("envelope", "lacrado", "protocolo presencial"),
        "Organizar envelopes e protocolo",
        "Conferir quantidade, identificação, lacre, ordem dos documentos e endereço de entrega.",
    ),
    (
        "Procedimentos",
        ("assinatura digital", "certificado digital", "portal de compras", "sistema eletronico", "sistema eletrônico"),
        "Validar credenciamento e forma de envio eletrônico",
        "Testar acesso, certificado, procuração e permissões do usuário responsável pelo envio.",
    ),
    (
        "Proposta",
        ("validade da proposta", "prazo de validade", "planilha de custos", "proposta de precos", "proposta de preços"),
        "Conferir validade e composição da proposta",
        "Revisar prazo de validade, planilhas, encargos, descontos e critérios de aceitabilidade.",
    ),
    (
        "Prazos",
        ("pedido de esclarecimento", "impugnacao", "impugnação", "recurso administrativo"),
        "Registrar prazos de esclarecimento, impugnação e recurso",
        "Mapear os prazos processuais e definir responsáveis pelo acompanhamento.",
    ),
)


def _local_items(edital: Edital, rows: list[tuple[Chunk, Document]]) -> list[dict[str, Any]]:
    items = _default_items(edital)
    found: OrderedDict[str, dict[str, Any]] = OrderedDict()
    for chunk, document in rows:
        normalized = _normalize(chunk.content)
        sentences = re.split(r"(?<=[.!?;:])\s+|\n+", chunk.content)
        source = _source_label(document.title, chunk.page_number)
        for category, keywords, title, description in RULES:
            if not any(_normalize(keyword) in normalized for keyword in keywords):
                continue
            evidence = ""
            for sentence in sentences:
                sentence_normalized = _normalize(sentence)
                if any(_normalize(keyword) in sentence_normalized for keyword in keywords):
                    evidence = _clean_sentence(sentence)
                    break
            key = f"{category}:{title}"
            current = found.get(key)
            candidate = {
                "category": category,
                "title": title,
                "description": evidence or description,
                "required": True,
                "source_reference": source,
            }
            if current is None or len(str(candidate["description"])) > len(str(current["description"])):
                found[key] = candidate
    items.extend(found.values())
    # Evita um checklist genérico excessivamente curto quando o documento contém texto,
    # mas poucas palavras-chave reconhecidas.
    if rows and len(items) < 7:
        items.extend(
            [
                {
                    "category": "Procedimentos",
                    "title": "Revisar anexos e modelos do edital",
                    "description": "Conferir se todos os anexos, formulários e modelos mencionados estão disponíveis e atualizados.",
                    "required": True,
                    "source_reference": "Documentos indexados",
                },
                {
                    "category": "Prazos",
                    "title": "Criar agenda interna de entregas",
                    "description": "Definir responsáveis e datas internas anteriores ao prazo oficial para revisão e protocolo.",
                    "required": True,
                    "source_reference": "Planejamento interno",
                },
            ]
        )
    return items[:30]


def _sanitize_items(items: list[dict[str, Any]], fallback_reference: str) -> list[dict[str, Any]]:
    clean: list[dict[str, Any]] = []
    seen: set[str] = set()
    for raw in items:
        title = _clean_sentence(str(raw.get("title") or ""), 500)
        if len(title) < 4:
            continue
        key = _normalize(title)
        if key in seen:
            continue
        seen.add(key)
        category = _clean_sentence(str(raw.get("category") or "Geral"), 120) or "Geral"
        description = _clean_sentence(str(raw.get("description") or ""), 1200) or None
        source_reference = _clean_sentence(
            str(raw.get("source_reference") or fallback_reference), 700
        ) or fallback_reference
        clean.append(
            {
                "category": category,
                "title": title,
                "description": description,
                "required": bool(raw.get("required", True)),
                "source_reference": source_reference,
            }
        )
    return clean[:30]


def generate_checklist(
    database: Session,
    edital_id: str,
    *,
    replace_existing: bool = True,
) -> tuple[list[ChecklistItem], str]:
    edital = database.get(Edital, edital_id)
    if not edital:
        raise ValueError("Edital não encontrado")

    rows = _context_rows(database, edital_id)
    context_blocks = [
        f"[Documento: {document.title} | {_source_label(document.title, chunk.page_number)}]\n{chunk.content}"
        for chunk, document in rows[:80]
    ]
    summary = (
        f"Título: {edital.title}\nÓrgão: {edital.organization or 'Não informado'}\n"
        f"Modalidade: {edital.modality_name or edital.source}\nObjeto: {edital.object_text or 'Não informado'}"
    )

    ai = AIProvider()
    generated, mode = ai.checklist_from_context(summary, context_blocks)
    if not generated:
        generated = _local_items(edital, rows)
        mode = "local"
    clean = _sanitize_items(generated, "Análise dos documentos indexados")
    if not clean:
        clean = _sanitize_items(_default_items(edital), "Metadados do edital")

    if replace_existing:
        database.execute(delete(ChecklistItem).where(ChecklistItem.edital_id == edital_id))

    records: list[ChecklistItem] = []
    for position, item in enumerate(clean, start=1):
        record = ChecklistItem(
            edital_id=edital_id,
            category=str(item["category"]),
            title=str(item["title"]),
            description=item.get("description"),
            required=bool(item.get("required", True)),
            status="pendente",
            source_reference=str(item.get("source_reference") or "Análise do edital"),
            generated_by_ai=True,
            position=position,
        )
        database.add(record)
        records.append(record)
    database.commit()
    for record in records:
        database.refresh(record)
    return records, mode
