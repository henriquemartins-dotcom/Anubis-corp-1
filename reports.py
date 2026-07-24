from __future__ import annotations

from datetime import datetime
import re
import unicodedata
from pathlib import Path
from typing import Iterable

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import (
    KeepTogether,
    PageBreak,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.config import get_settings
from app.models import Edital
from app.pipeline import priority_label, stage_label

settings = get_settings()

BORDEAUX = colors.HexColor("#1B314A")
DARK_BORDEAUX = colors.HexColor("#13263A")
GOLD = colors.HexColor("#B89453")
LIGHT = colors.HexColor("#F8F3EA")
LIGHT_2 = colors.HexColor("#EFE5D8")
TEXT = colors.HexColor("#293441")
MUTED = colors.HexColor("#776C62")
GREEN = colors.HexColor("#18794E")
GRAY = colors.HexColor("#DED1C3")


def _money(value: float | None) -> str:
    if value is None:
        return "Não informado"
    rendered = f"{float(value):,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    return f"R$ {rendered}"


def _date(value) -> str:
    return value.strftime("%d/%m/%Y %H:%M") if value else "Não informado"


def _escape(value: object) -> str:
    return (
        str(value or "")
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
    )


def _status_label(status: str) -> str:
    return {
        "pendente": "Pendente",
        "em_andamento": "Em andamento",
        "concluido": "Concluído",
        "nao_aplicavel": "Não aplicável",
    }.get(status, status.replace("_", " ").title())


class NumberedCanvasMixin:
    pass


def _header_footer(canvas, document) -> None:
    canvas.saveState()
    width, height = A4
    canvas.setStrokeColor(GRAY)
    canvas.setLineWidth(0.5)
    canvas.line(18 * mm, 15 * mm, width - 18 * mm, 15 * mm)
    canvas.setFont("Helvetica", 8)
    canvas.setFillColor(MUTED)
    canvas.drawString(18 * mm, 10 * mm, "Hórus Connective Licitações - Relatório de Concorrências")
    canvas.drawRightString(width - 18 * mm, 10 * mm, f"Página {document.page}")
    canvas.restoreState()


def _styles():
    sample = getSampleStyleSheet()
    return {
        "cover_kicker": ParagraphStyle(
            "cover_kicker",
            parent=sample["Normal"],
            fontName="Helvetica-Bold",
            fontSize=9,
            leading=12,
            textColor=GOLD,
            spaceAfter=8,
        ),
        "cover_title": ParagraphStyle(
            "cover_title",
            parent=sample["Title"],
            fontName="Helvetica-Bold",
            fontSize=25,
            leading=29,
            textColor=colors.white,
            alignment=TA_LEFT,
            spaceAfter=10,
        ),
        "cover_subtitle": ParagraphStyle(
            "cover_subtitle",
            parent=sample["Normal"],
            fontName="Helvetica",
            fontSize=11,
            leading=16,
            textColor=colors.HexColor("#EDE3D4"),
        ),
        "h1": ParagraphStyle(
            "h1",
            parent=sample["Heading1"],
            fontName="Helvetica-Bold",
            fontSize=17,
            leading=21,
            textColor=DARK_BORDEAUX,
            spaceBefore=6,
            spaceAfter=10,
        ),
        "h2": ParagraphStyle(
            "h2",
            parent=sample["Heading2"],
            fontName="Helvetica-Bold",
            fontSize=12,
            leading=15,
            textColor=BORDEAUX,
            spaceBefore=10,
            spaceAfter=6,
        ),
        "body": ParagraphStyle(
            "body",
            parent=sample["BodyText"],
            fontName="Helvetica",
            fontSize=9.2,
            leading=13.5,
            textColor=TEXT,
            spaceAfter=6,
        ),
        "small": ParagraphStyle(
            "small",
            parent=sample["BodyText"],
            fontName="Helvetica",
            fontSize=7.8,
            leading=10.5,
            textColor=MUTED,
        ),
        "table": ParagraphStyle(
            "table",
            parent=sample["BodyText"],
            fontName="Helvetica",
            fontSize=7.4,
            leading=9.2,
            textColor=TEXT,
        ),
        "table_bold": ParagraphStyle(
            "table_bold",
            parent=sample["BodyText"],
            fontName="Helvetica-Bold",
            fontSize=7.4,
            leading=9.2,
            textColor=TEXT,
        ),
        "table_header": ParagraphStyle(
            "table_header",
            parent=sample["BodyText"],
            fontName="Helvetica-Bold",
            fontSize=7.4,
            leading=9.2,
            textColor=colors.white,
        ),
        "center": ParagraphStyle(
            "center",
            parent=sample["BodyText"],
            fontName="Helvetica-Bold",
            fontSize=9,
            leading=12,
            alignment=TA_CENTER,
            textColor=TEXT,
        ),
        "right": ParagraphStyle(
            "right",
            parent=sample["BodyText"],
            fontName="Helvetica-Bold",
            fontSize=9,
            leading=12,
            alignment=TA_RIGHT,
            textColor=TEXT,
        ),
    }


def _summary_table(editais: list[Edital], styles) -> Table:
    active = [item for item in editais if item.pipeline_stage not in {"ganha", "perdida_arquivada"}]
    total_value = sum(float(item.estimated_value or 0) for item in editais)
    completed = sum(item.checklist_completed for item in editais)
    checklist_total = sum(item.checklist_total for item in editais)
    data = [
        [
            Paragraph("CONCORRÊNCIAS", styles["small"]),
            Paragraph("ATIVAS", styles["small"]),
            Paragraph("VALOR MAPEADO", styles["small"]),
            Paragraph("CHECKLIST", styles["small"]),
        ],
        [
            Paragraph(str(len(editais)), styles["center"]),
            Paragraph(str(len(active)), styles["center"]),
            Paragraph(_money(total_value), styles["center"]),
            Paragraph(f"{completed}/{checklist_total}", styles["center"]),
        ],
    ]
    table = Table(data, colWidths=[38 * mm, 38 * mm, 52 * mm, 38 * mm])
    table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), LIGHT_2),
                ("BACKGROUND", (0, 1), (-1, 1), colors.white),
                ("BOX", (0, 0), (-1, -1), 0.6, GRAY),
                ("INNERGRID", (0, 0), (-1, -1), 0.4, GRAY),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("ALIGN", (0, 0), (-1, -1), "CENTER"),
                ("TOPPADDING", (0, 0), (-1, -1), 7),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 7),
            ]
        )
    )
    return table


def generate_competition_report(
    database: Session,
    edital_ids: Iterable[str],
    *,
    title: str = "Relatório de Concorrências Selecionadas",
    output_dir: Path | None = None,
) -> Path:
    ids = list(dict.fromkeys(str(value) for value in edital_ids if value))
    if not ids:
        raise ValueError("Selecione ao menos uma concorrência para gerar o relatório")

    statement = (
        select(Edital)
        .options(selectinload(Edital.pipeline), selectinload(Edital.checklist_items))
        .where(Edital.id.in_(ids))
    )
    by_id = {item.id: item for item in database.scalars(statement).all()}
    editais = [by_id[item_id] for item_id in ids if item_id in by_id]
    if not editais:
        raise ValueError("Nenhum edital selecionado foi encontrado")

    reports_dir = output_dir or (settings.data_dir / "reports")
    reports_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    target = reports_dir / f"Relatorio_Concorrencias_HORUS_CONNECTIVE_{timestamp}.pdf"
    styles = _styles()

    doc = SimpleDocTemplate(
        str(target),
        pagesize=A4,
        rightMargin=18 * mm,
        leftMargin=18 * mm,
        topMargin=18 * mm,
        bottomMargin=22 * mm,
        title=title,
        author="Hórus Connective Licitações - Família Connective",
        subject="Relatório executivo de concorrências selecionadas",
    )

    story = []
    cover = Table(
        [
            [
                Paragraph(
                    "HÓRUS CONNECTIVE · LICITAÇÕES",
                    styles["cover_kicker"],
                )
            ],
            [Paragraph(_escape(title), styles["cover_title"])],
            [
                Paragraph(
                    "Consolidação executiva das oportunidades escolhidas, com prazos, valores, "
                    "etapas do pipeline e andamento dos checklists.",
                    styles["cover_subtitle"],
                )
            ],
            [
                Paragraph(
                    f"Gerado em {datetime.now().strftime('%d/%m/%Y às %H:%M')} - {len(editais)} concorrência(s)",
                    styles["cover_subtitle"],
                )
            ],
        ],
        colWidths=[174 * mm],
    )
    cover.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, -1), DARK_BORDEAUX),
                ("BOX", (0, 0), (-1, -1), 0.8, BORDEAUX),
                ("LEFTPADDING", (0, 0), (-1, -1), 18),
                ("RIGHTPADDING", (0, 0), (-1, -1), 18),
                ("TOPPADDING", (0, 0), (-1, 0), 22),
                ("TOPPADDING", (0, 1), (-1, 1), 8),
                ("BOTTOMPADDING", (0, 3), (-1, 3), 24),
                ("BOTTOMPADDING", (0, 0), (-1, 2), 8),
            ]
        )
    )
    story.extend([cover, Spacer(1, 12 * mm), _summary_table(editais, styles), Spacer(1, 10 * mm)])
    story.append(Paragraph("Visão consolidada", styles["h1"]))

    overview = [[
        Paragraph("Concorrência", styles["table_header"]),
        Paragraph("Órgão / UF", styles["table_header"]),
        Paragraph("Etapa", styles["table_header"]),
        Paragraph("Prazo", styles["table_header"]),
        Paragraph("Valor", styles["table_header"]),
    ]]
    for edital in editais:
        overview.append(
            [
                Paragraph(_escape(edital.title), styles["table"]),
                Paragraph(_escape(f"{edital.organization or 'Não informado'} / {edital.uf or 'BR'}"), styles["table"]),
                Paragraph(_escape(stage_label(edital.pipeline_stage)), styles["table"]),
                Paragraph(_escape(_date(edital.proposal_end)), styles["table"]),
                Paragraph(_escape(_money(edital.estimated_value)), styles["table"]),
            ]
        )
    overview_table = Table(overview, colWidths=[55 * mm, 41 * mm, 29 * mm, 27 * mm, 24 * mm], repeatRows=1)
    overview_table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), BORDEAUX),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                ("GRID", (0, 0), (-1, -1), 0.35, GRAY),
                ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, LIGHT]),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("LEFTPADDING", (0, 0), (-1, -1), 5),
                ("RIGHTPADDING", (0, 0), (-1, -1), 5),
                ("TOPPADDING", (0, 0), (-1, -1), 6),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
            ]
        )
    )
    story.extend([overview_table, PageBreak()])

    for index, edital in enumerate(editais, start=1):
        story.append(Paragraph(f"{index}. {_escape(edital.title)}", styles["h1"]))
        details = [
            [Paragraph("Órgão", styles["small"]), Paragraph(_escape(edital.organization or "Não informado"), styles["body"])],
            [Paragraph("Localidade", styles["small"]), Paragraph(_escape(f"{edital.municipality or 'Não informado'} / {edital.uf or 'BR'}"), styles["body"])],
            [Paragraph("Modalidade", styles["small"]), Paragraph(_escape(edital.modality_name or edital.source), styles["body"])],
            [Paragraph("Etapa / Prioridade", styles["small"]), Paragraph(_escape(f"{stage_label(edital.pipeline_stage)} / {priority_label(edital.pipeline_priority)}"), styles["body"])],
            [Paragraph("Responsável", styles["small"]), Paragraph(_escape(edital.pipeline_responsible or "Não definido"), styles["body"])],
            [Paragraph("Encerramento", styles["small"]), Paragraph(_escape(_date(edital.proposal_end)), styles["body"])],
            [Paragraph("Valor estimado", styles["small"]), Paragraph(_escape(_money(edital.estimated_value)), styles["body"])],
        ]
        details_table = Table(details, colWidths=[42 * mm, 132 * mm])
        details_table.setStyle(
            TableStyle(
                [
                    ("BACKGROUND", (0, 0), (0, -1), LIGHT_2),
                    ("GRID", (0, 0), (-1, -1), 0.35, GRAY),
                    ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                    ("LEFTPADDING", (0, 0), (-1, -1), 7),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 7),
                    ("TOPPADDING", (0, 0), (-1, -1), 5),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
                ]
            )
        )
        story.extend([details_table, Spacer(1, 5 * mm)])
        story.append(Paragraph("Objeto", styles["h2"]))
        story.append(Paragraph(_escape(edital.object_text or "Objeto não informado."), styles["body"]))

        checklist = list(edital.checklist_items or [])
        story.append(Paragraph("Checklist operacional", styles["h2"]))
        if checklist:
            checklist_data = [[
                Paragraph("Status", styles["table_header"]),
                Paragraph("Categoria", styles["table_header"]),
                Paragraph("Item", styles["table_header"]),
                Paragraph("Referência", styles["table_header"]),
            ]]
            for item in checklist:
                checklist_data.append(
                    [
                        Paragraph(_escape(_status_label(item.status)), styles["table"]),
                        Paragraph(_escape(item.category), styles["table"]),
                        Paragraph(
                            f"<b>{_escape(item.title)}</b>" + (f"<br/>{_escape(item.description)}" if item.description else ""),
                            styles["table"],
                        ),
                        Paragraph(_escape(item.source_reference or "-"), styles["table"]),
                    ]
                )
            checklist_table = Table(
                checklist_data,
                colWidths=[24 * mm, 32 * mm, 80 * mm, 38 * mm],
                repeatRows=1,
            )
            checklist_table.setStyle(
                TableStyle(
                    [
                        ("BACKGROUND", (0, 0), (-1, 0), BORDEAUX),
                        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                        ("GRID", (0, 0), (-1, -1), 0.35, GRAY),
                        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, LIGHT]),
                        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                        ("LEFTPADDING", (0, 0), (-1, -1), 5),
                        ("RIGHTPADDING", (0, 0), (-1, -1), 5),
                        ("TOPPADDING", (0, 0), (-1, -1), 5),
                        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
                    ]
                )
            )
            story.append(checklist_table)
        else:
            story.append(
                Paragraph(
                    "Checklist ainda não gerado. Abra o edital no Hórus Connective e utilize a opção Gerar checklist com IA.",
                    styles["body"],
                )
            )

        if edital.pipeline_notes:
            story.extend(
                [
                    Paragraph("Observações internas", styles["h2"]),
                    Paragraph(_escape(edital.pipeline_notes), styles["body"]),
                ]
            )
        story.append(Spacer(1, 5 * mm))
        story.append(
            Paragraph(
                "Nota: este relatório é um instrumento de apoio. A equipe deve validar todas as informações no edital e nos documentos oficiais.",
                styles["small"],
            )
        )
        if index < len(editais):
            story.append(PageBreak())

    doc.build(story, onFirstPage=_header_footer, onLaterPages=_header_footer)
    return target



def _safe_filename(value: str, max_length: int = 70) -> str:
    ascii_value = unicodedata.normalize("NFKD", value or "edital").encode("ascii", "ignore").decode("ascii")
    normalized = re.sub(r"[^A-Za-z0-9_-]+", "_", ascii_value).strip("_")
    return (normalized or "edital")[:max_length]


def _checklist_header_footer(canvas, document) -> None:
    canvas.saveState()
    width, _height = A4
    canvas.setStrokeColor(GRAY)
    canvas.setLineWidth(0.5)
    canvas.line(15 * mm, 14 * mm, width - 15 * mm, 14 * mm)
    canvas.setFont("Helvetica", 7.5)
    canvas.setFillColor(MUTED)
    canvas.drawString(15 * mm, 9 * mm, "Hórus Connective Licitações - Checklist Operacional do Edital")
    canvas.drawRightString(width - 15 * mm, 9 * mm, f"Página {document.page}")
    canvas.restoreState()


def _checklist_styles():
    sample = getSampleStyleSheet()
    return {
        "title": ParagraphStyle(
            "checklist_title",
            parent=sample["Title"],
            fontName="Helvetica-Bold",
            fontSize=20,
            leading=24,
            textColor=DARK_BORDEAUX,
            alignment=TA_CENTER,
            spaceAfter=7,
        ),
        "subtitle": ParagraphStyle(
            "checklist_subtitle",
            parent=sample["Normal"],
            fontName="Helvetica",
            fontSize=10.5,
            leading=14,
            textColor=MUTED,
            alignment=TA_CENTER,
            spaceAfter=10,
        ),
        "section": ParagraphStyle(
            "checklist_section",
            parent=sample["Heading1"],
            fontName="Helvetica-Bold",
            fontSize=15.5,
            leading=19,
            textColor=DARK_BORDEAUX,
            spaceBefore=9,
            spaceAfter=6,
            keepWithNext=True,
        ),
        "body": ParagraphStyle(
            "checklist_body",
            parent=sample["BodyText"],
            fontName="Helvetica",
            fontSize=8.4,
            leading=11.2,
            textColor=TEXT,
        ),
        "body_bold": ParagraphStyle(
            "checklist_body_bold",
            parent=sample["BodyText"],
            fontName="Helvetica-Bold",
            fontSize=8.4,
            leading=11.2,
            textColor=TEXT,
        ),
        "small": ParagraphStyle(
            "checklist_small",
            parent=sample["BodyText"],
            fontName="Helvetica",
            fontSize=7.2,
            leading=9.2,
            textColor=MUTED,
        ),
        "table": ParagraphStyle(
            "checklist_table",
            parent=sample["BodyText"],
            fontName="Helvetica",
            fontSize=7.1,
            leading=9.1,
            textColor=TEXT,
        ),
        "table_bold": ParagraphStyle(
            "checklist_table_bold",
            parent=sample["BodyText"],
            fontName="Helvetica-Bold",
            fontSize=7.1,
            leading=9.1,
            textColor=TEXT,
        ),
        "table_header": ParagraphStyle(
            "checklist_table_header",
            parent=sample["BodyText"],
            fontName="Helvetica-Bold",
            fontSize=7.2,
            leading=9.2,
            textColor=colors.white,
        ),
        "callout": ParagraphStyle(
            "checklist_callout",
            parent=sample["BodyText"],
            fontName="Helvetica",
            fontSize=8.5,
            leading=11.5,
            textColor=TEXT,
        ),
        "callout_bold": ParagraphStyle(
            "checklist_callout_bold",
            parent=sample["BodyText"],
            fontName="Helvetica-Bold",
            fontSize=8.5,
            leading=11.5,
            textColor=TEXT,
        ),
        "center": ParagraphStyle(
            "checklist_center",
            parent=sample["BodyText"],
            fontName="Helvetica-Bold",
            fontSize=8,
            leading=10,
            alignment=TA_CENTER,
            textColor=TEXT,
        ),
    }


def _callout_table(label: str, text: str, styles, *, background, border) -> Table:
    content = Paragraph(f"<b>{_escape(label)}:</b> {_escape(text)}", styles["callout"])
    table = Table([[content]], colWidths=[180 * mm])
    table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, -1), background),
                ("BOX", (0, 0), (-1, -1), 0.7, border),
                ("LEFTPADDING", (0, 0), (-1, -1), 8),
                ("RIGHTPADDING", (0, 0), (-1, -1), 8),
                ("TOPPADDING", (0, 0), (-1, -1), 7),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 7),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ]
        )
    )
    return table


def _checklist_mark(status: str) -> str:
    return {
        "concluido": "[X]",
        "nao_aplicavel": "[-]",
        "em_andamento": "[~]",
    }.get(status, "[ ]")


def generate_checklist_report(
    database: Session,
    edital_id: str,
    *,
    output_dir: Path | None = None,
) -> Path:
    statement = (
        select(Edital)
        .options(selectinload(Edital.pipeline), selectinload(Edital.checklist_items))
        .where(Edital.id == edital_id)
    )
    edital = database.scalar(statement)
    if not edital:
        raise ValueError("Edital não encontrado")

    checklist = sorted(
        list(edital.checklist_items or []),
        key=lambda item: (item.position, item.category.lower(), item.title.lower()),
    )
    if not checklist:
        raise ValueError("Gere o checklist do edital antes de baixar o PDF")

    reports_dir = output_dir or (settings.data_dir / "reports" / "checklists")
    reports_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    target = reports_dir / f"Checklist_Operacional_HORUS_CONNECTIVE_{_safe_filename(edital.title)}_{timestamp}.pdf"
    styles = _checklist_styles()

    doc = SimpleDocTemplate(
        str(target),
        pagesize=A4,
        rightMargin=15 * mm,
        leftMargin=15 * mm,
        topMargin=14 * mm,
        bottomMargin=19 * mm,
        title=f"Checklist Operacional - {edital.title}",
        author="Hórus Connective Licitações - Família Connective",
        subject="Checklist operacional gerado por inteligência artificial",
    )

    applicable = [item for item in checklist if item.status != "nao_aplicavel"]
    completed = sum(1 for item in applicable if item.status == "concluido")
    pending = sum(1 for item in applicable if item.status == "pendente")
    in_progress = sum(1 for item in applicable if item.status == "em_andamento")
    progress = round((completed / len(applicable)) * 100) if applicable else 0
    required_pending = sum(1 for item in checklist if item.required and item.status not in {"concluido", "nao_aplicavel"})

    fact_parts = [
        f"Contratante: {edital.organization or 'Não informado'}",
        f"Objeto: {edital.object_text or 'Não informado'}",
        f"Modalidade: {edital.modality_name or edital.source}",
        f"Valor estimado: {_money(edital.estimated_value)}",
        f"Encerramento: {_date(edital.proposal_end)}",
    ]
    alert = (
        f"Existem {required_pending} item(ns) obrigatório(s) ainda não concluído(s). "
        f"O prazo registrado é {_date(edital.proposal_end)}. "
        "Valide o checklist no edital oficial antes do protocolo ou da sessão."
    )

    story = [
        Paragraph("CHECKLIST OPERACIONAL DO EDITAL", styles["title"]),
        Paragraph(
            _escape(f"{edital.title} | {edital.organization or 'Órgão não informado'}"),
            styles["subtitle"],
        ),
        _callout_table("FATO DO EDITAL", ". ".join(fact_parts) + ".", styles, background=LIGHT_2, border=BORDEAUX),
        Spacer(1, 6 * mm),
        _callout_table("ALERTA CENTRAL", alert, styles, background=colors.HexColor("#FFF2CC"), border=GOLD),
        Spacer(1, 8 * mm),
        Paragraph("1. Dados do certame", styles["section"]),
    ]

    location = " / ".join(value for value in [edital.municipality, edital.uf] if value) or "Não informado"
    facts = [
        ("Órgão", edital.organization or "Não informado", "[ ] Conferido"),
        ("Processo", edital.process_number or edital.purchase_number or edital.pncp_id or "Não informado", "[ ] Conferido"),
        ("Modalidade/tipo", edital.modality_name or edital.source, "[ ] Conferido"),
        ("Objeto", edital.object_text or "Não informado", "[ ] Conferido"),
        ("Valor estimado", _money(edital.estimated_value), "[ ] Validar viabilidade"),
        ("Encerramento", _date(edital.proposal_end), "[ ] Agendar"),
        ("Localidade", location, "[ ] Logística"),
        ("Etapa do pipeline", stage_label(edital.pipeline_stage), "[ ] Atualizar"),
        ("Responsável geral", edital.pipeline_responsible or "Não definido", "[ ] Definir"),
        ("Fonte oficial", edital.source_url or edital.source, "[ ] Monitorar"),
    ]
    fact_data = [[
        Paragraph("Campo", styles["table_header"]),
        Paragraph("Informação extraída do edital", styles["table_header"]),
        Paragraph("Controle", styles["table_header"]),
    ]]
    for field, value, control in facts:
        fact_data.append([
            Paragraph(_escape(field), styles["table"]),
            Paragraph(_escape(value), styles["table"]),
            Paragraph(_escape(control), styles["table"]),
        ])
    fact_table = Table(fact_data, colWidths=[36 * mm, 105 * mm, 39 * mm], repeatRows=1)
    fact_table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), BORDEAUX),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("GRID", (0, 0), (-1, -1), 0.45, colors.HexColor("#3B2A2E")),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("LEFTPADDING", (0, 0), (-1, -1), 5),
        ("RIGHTPADDING", (0, 0), (-1, -1), 5),
        ("TOPPADDING", (0, 0), (-1, -1), 4.5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4.5),
    ]))
    story.extend([fact_table, Spacer(1, 7 * mm), Paragraph("2. Andamento geral", styles["section"])])

    summary_data = [
        [
            Paragraph("Total", styles["table_header"]),
            Paragraph("Concluídos", styles["table_header"]),
            Paragraph("Em andamento", styles["table_header"]),
            Paragraph("Pendentes", styles["table_header"]),
            Paragraph("Progresso", styles["table_header"]),
        ],
        [
            Paragraph(str(len(checklist)), styles["center"]),
            Paragraph(str(completed), styles["center"]),
            Paragraph(str(in_progress), styles["center"]),
            Paragraph(str(pending), styles["center"]),
            Paragraph(f"{progress}%", styles["center"]),
        ],
    ]
    summary_table = Table(summary_data, colWidths=[32 * mm, 36 * mm, 40 * mm, 34 * mm, 38 * mm])
    summary_table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), BORDEAUX),
        ("BACKGROUND", (0, 1), (-1, 1), colors.white),
        ("GRID", (0, 0), (-1, -1), 0.45, GRAY),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("ALIGN", (0, 0), (-1, -1), "CENTER"),
        ("TOPPADDING", (0, 0), (-1, -1), 6),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
    ]))
    story.append(summary_table)

    grouped: dict[str, list] = {}
    for item in checklist:
        grouped.setdefault(item.category or "Geral", []).append(item)

    section_number = 3
    for category, items in grouped.items():
        story.extend([Spacer(1, 6 * mm), Paragraph(f"{section_number}. {_escape(category)}", styles["section"])])
        category_data = [[
            Paragraph("Feito", styles["table_header"]),
            Paragraph("Item", styles["table_header"]),
            Paragraph("Responsável", styles["table_header"]),
            Paragraph("Exigência / controle", styles["table_header"]),
            Paragraph("Referência", styles["table_header"]),
        ]]
        for item in items:
            detail_parts = []
            if item.description:
                detail_parts.append(_escape(item.description))
            if item.notes:
                detail_parts.append(f"<b>Observação:</b> {_escape(item.notes)}")
            detail = "<br/>".join(detail_parts) or "Conferir exigência no documento oficial."
            category_data.append([
                Paragraph(_checklist_mark(item.status), styles["center"]),
                Paragraph(_escape(item.title), styles["table_bold"]),
                Paragraph(_escape(item.responsible or "A definir"), styles["table"]),
                Paragraph(detail, styles["table"]),
                Paragraph(_escape(item.source_reference or "Sem referência"), styles["small"]),
            ])
        category_table = Table(
            category_data,
            colWidths=[14 * mm, 42 * mm, 28 * mm, 64 * mm, 32 * mm],
            repeatRows=1,
        )
        category_table.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), BORDEAUX),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
            ("GRID", (0, 0), (-1, -1), 0.45, colors.HexColor("#3B2A2E")),
            ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, LIGHT]),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("ALIGN", (0, 1), (0, -1), "CENTER"),
            ("LEFTPADDING", (0, 0), (-1, -1), 4.5),
            ("RIGHTPADDING", (0, 0), (-1, -1), 4.5),
            ("TOPPADDING", (0, 0), (-1, -1), 4.5),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 4.5),
        ]))
        story.append(category_table)
        section_number += 1

    responsible_groups: dict[str, list[str]] = {}
    for item in checklist:
        if item.status in {"concluido", "nao_aplicavel"}:
            continue
        responsible = item.responsible or "A definir"
        responsible_groups.setdefault(responsible, []).append(item.title)
    if responsible_groups:
        story.extend([Spacer(1, 7 * mm), Paragraph(f"{section_number}. Próximos passos por responsável", styles["section"])])
        next_data = [[
            Paragraph("Responsável", styles["table_header"]),
            Paragraph("Próximas ações", styles["table_header"]),
        ]]
        for responsible, titles in sorted(responsible_groups.items()):
            next_data.append([
                Paragraph(_escape(responsible), styles["table"]),
                Paragraph(_escape("; ".join(titles)), styles["table"]),
            ])
        next_table = Table(next_data, colWidths=[44 * mm, 136 * mm], repeatRows=1)
        next_table.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), BORDEAUX),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
            ("GRID", (0, 0), (-1, -1), 0.45, colors.HexColor("#3B2A2E")),
            ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, LIGHT]),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("LEFTPADDING", (0, 0), (-1, -1), 5),
            ("RIGHTPADDING", (0, 0), (-1, -1), 5),
            ("TOPPADDING", (0, 0), (-1, -1), 5),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
        ]))
        story.append(next_table)

    recommendation = (
        f"Progresso atual de {progress}%. "
        f"Há {pending} item(ns) pendente(s), {in_progress} em andamento e {required_pending} obrigatório(s) ainda não concluído(s). "
        "A equipe deve realizar conferência cruzada com o edital, anexos, retificações e publicações oficiais antes da entrega."
    )
    story.extend([
        Spacer(1, 7 * mm),
        _callout_table(
            "RECOMENDAÇÃO OPERACIONAL",
            recommendation,
            styles,
            background=colors.HexColor("#E6F2DE") if progress >= 80 else colors.HexColor("#FFF2CC"),
            border=GREEN if progress >= 80 else GOLD,
        ),
        Spacer(1, 4 * mm),
        Paragraph(
            "Legenda: [ ] pendente | [~] em andamento | [X] concluído | [-] não aplicável. Documento gerado automaticamente; valide todas as informações no edital oficial.",
            styles["small"],
        ),
    ])

    doc.build(story, onFirstPage=_checklist_header_footer, onLaterPages=_checklist_header_footer)
    return target
