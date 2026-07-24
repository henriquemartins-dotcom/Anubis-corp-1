from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from app.db import Base
from app.models import ChecklistItem, Chunk, Document, Edital
from app.services.checklists import generate_checklist


def make_session() -> Session:
    engine = create_engine("sqlite+pysqlite:///:memory:", connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    return Session(engine, expire_on_commit=False)


def test_local_checklist_uses_indexed_edital_requirements(monkeypatch):
    monkeypatch.setenv("AI_MODE", "local")
    with make_session() as database:
        edital = Edital(
            title="Concorrência de publicidade",
            organization="Secretaria de Comunicação",
            object_text="Contratação de agência de publicidade",
            indexing_status="indexed",
        )
        document = Document(edital=edital, title="Edital completo", status="indexed")
        chunk = Chunk(
            edital=edital,
            document=document,
            page_number=12,
            chunk_index=0,
            content=(
                "A licitante deverá apresentar certidão negativa de débitos, CNDT e regularidade do FGTS. "
                "Também será exigido atestado de capacidade técnica, balanço patrimonial e as declarações "
                "constantes dos anexos. Os envelopes deverão ser lacrados."
            ),
            embedding=[0.1, 0.2],
        )
        database.add_all([edital, document, chunk])
        database.commit()

        items, mode = generate_checklist(database, edital.id)

        titles = {item.title for item in items}
        assert mode == "local"
        assert len(items) >= 8
        assert "Conferir certidões fiscais e trabalhistas" in titles
        assert "Reunir comprovação de capacidade técnica" in titles
        assert "Preparar qualificação econômico-financeira" in titles
        assert "Organizar envelopes e protocolo" in titles
        assert database.scalar(
            select(ChecklistItem).where(ChecklistItem.edital_id == edital.id)
        ) is not None


def test_regenerating_checklist_replaces_existing_items(monkeypatch):
    monkeypatch.setenv("AI_MODE", "local")
    with make_session() as database:
        edital = Edital(title="Pregão eletrônico")
        database.add(edital)
        database.commit()

        first, _ = generate_checklist(database, edital.id)
        first_ids = {item.id for item in first}
        second, _ = generate_checklist(database, edital.id, replace_existing=True)
        second_ids = {item.id for item in second}

        assert first_ids.isdisjoint(second_ids)
        stored = list(database.scalars(select(ChecklistItem).where(ChecklistItem.edital_id == edital.id)))
        assert len(stored) == len(second)
