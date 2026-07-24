from pathlib import Path

import fitz
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.db import Base
from app.models import BidPipeline, ChecklistItem, Edital
from app.services.reports import generate_competition_report


def make_session() -> Session:
    engine = create_engine("sqlite+pysqlite:///:memory:", connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    return Session(engine, expire_on_commit=False)


def test_competition_report_generates_readable_pdf(tmp_path: Path):
    with make_session() as database:
        edital = Edital(
            title="Concorrência Pública de Comunicação Institucional",
            organization="Assembleia Legislativa do Estado do Espírito Santo",
            municipality="Vitória",
            uf="ES",
            modality_name="Concorrência",
            estimated_value=850000.50,
            object_text=(
                "Contratação de agência para planejamento, criação, produção e execução de serviços "
                "de publicidade e comunicação institucional."
            ),
        )
        edital.pipeline = BidPipeline(stage="em_analise", priority="alta", responsible="Henrique")
        edital.checklist_items = [
            ChecklistItem(
                category="Habilitação",
                title="Validar certidões",
                description="Conferir validade da CND, FGTS e CNDT.",
                source_reference="Edital - p. 42",
                status="em_andamento",
                position=1,
            ),
            ChecklistItem(
                category="Proposta",
                title="Preparar proposta técnica",
                description="Montar os cadernos conforme a ordem indicada.",
                source_reference="Edital - p. 70",
                status="pendente",
                position=2,
            ),
        ]
        database.add(edital)
        database.commit()

        path = generate_competition_report(database, [edital.id], output_dir=tmp_path)

        assert path.exists()
        assert path.read_bytes().startswith(b"%PDF-")
        with fitz.open(path) as pdf:
            assert pdf.page_count >= 2
            text = "\n".join(page.get_text() for page in pdf)
        assert "Relatório de" in text
        assert "Concorrências\nSelecionadas" in text
        assert "Validar certidões" in text
        assert "Assembleia Legislativa" in text


def test_checklist_report_generates_printable_pdf(tmp_path: Path):
    from app.services.reports import generate_checklist_report

    with make_session() as database:
        edital = Edital(
            title="Concorrência nº 001/2026 - Publicidade e Propaganda",
            organization="Assembleia Legislativa do Estado do Espírito Santo - ALES",
            municipality="Vitória",
            uf="ES",
            modality_name="Concorrência - Melhor Técnica",
            estimated_value=6000000.00,
            object_text="Contratação de serviços de publicidade por intermédio de agência de propaganda.",
        )
        edital.pipeline = BidPipeline(stage="em_analise", priority="alta", responsible="Henrique")
        edital.checklist_items = [
            ChecklistItem(
                category="Cronograma e prazos",
                title="Entregar invólucros dentro do horário",
                description="Protocolar os invólucros até 13h45 na data da sessão.",
                source_reference="Edital - item 4.2",
                responsible="Administrativo",
                status="em_andamento",
                position=1,
            ),
            ChecklistItem(
                category="Habilitação",
                title="Conferir certidões fiscais e trabalhistas",
                description="Validar regularidade federal, estadual, municipal, FGTS e CNDT.",
                source_reference="Edital - p. 42",
                responsible="Administrativo/Jurídico",
                status="pendente",
                position=2,
            ),
            ChecklistItem(
                category="Proposta técnica",
                title="Revisar anonimato da via não identificada",
                description="Remover marcas, metadados, nomes e sinais que identifiquem a licitante.",
                source_reference="Edital - p. 18",
                responsible="Revisão final",
                status="concluido",
                position=3,
            ),
        ]
        database.add(edital)
        database.commit()

        path = generate_checklist_report(database, edital.id, output_dir=tmp_path)

        assert path.exists()
        assert path.read_bytes().startswith(b"%PDF-")
        with fitz.open(path) as pdf:
            assert pdf.page_count >= 2
            text = "\n".join(page.get_text() for page in pdf)
        assert "CHECKLIST OPERACIONAL DO EDITAL" in text
        assert "FATO DO EDITAL" in text
        assert "ALERTA CENTRAL" in text
        assert "Conferir certidões" in text
        assert "Próximos passos" in text or "Proximos passos" in text
