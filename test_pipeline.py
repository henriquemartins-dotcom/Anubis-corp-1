from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from app.db import Base
from app.main import update_pipeline
from app.models import BidPipelineEvent, Edital
from app.pipeline import PIPELINE_STAGE_LABELS
from app.schemas import PipelineUpdateRequest


def make_session() -> Session:
    engine = create_engine("sqlite+pysqlite:///:memory:", connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    return Session(engine, expire_on_commit=False)


def test_new_edital_starts_as_new_opportunity():
    with make_session() as database:
        edital = Edital(title="Concorrência de publicidade")
        database.add(edital)
        database.commit()
        assert edital.pipeline_stage == "nova_oportunidade"
        assert edital.pipeline_priority == "normal"


def test_pipeline_stage_update_creates_history():
    with make_session() as database:
        edital = Edital(title="Concorrência de comunicação")
        database.add(edital)
        database.commit()
        database.refresh(edital)

        updated = update_pipeline(
            edital.id,
            PipelineUpdateRequest(stage="triagem", priority="alta", responsible="Henrique"),
            database,
        )

        assert updated.pipeline_stage == "triagem"
        assert updated.pipeline_priority == "alta"
        assert updated.pipeline_responsible == "Henrique"
        event = database.scalar(select(BidPipelineEvent).where(BidPipelineEvent.edital_id == edital.id))
        assert event is not None
        assert event.from_stage == "nova_oportunidade"
        assert event.to_stage == "triagem"
        assert PIPELINE_STAGE_LABELS[event.to_stage] == "Triagem"


def test_pipeline_request_rejects_unknown_stage():
    try:
        PipelineUpdateRequest(stage="etapa_inexistente")
    except ValueError as error:
        assert "Etapa inválida" in str(error)
    else:
        raise AssertionError("Etapa inválida deveria ser rejeitada")
