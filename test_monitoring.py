from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.db import Base
from app.models import MonitorConfig
from app.services.monitoring import get_or_create_monitor_config, monitor_payload, queue_monitor_job


def make_session() -> Session:
    engine = create_engine("sqlite+pysqlite:///:memory:", connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    return Session(engine, expire_on_commit=False)


def test_monitor_config_is_created_with_safe_defaults():
    with make_session() as database:
        config = get_or_create_monitor_config(database)
        assert config.id == "default"
        assert config.hour == 7
        assert config.modalities == [6, 4, 8]
        assert database.get(MonitorConfig, "default") is not None


def test_monitor_payload_uses_selected_filters():
    with make_session() as database:
        config = get_or_create_monitor_config(database)
        config.lookback_days = 3
        config.modalities = [6, 8]
        config.uf = "ES"
        config.keywords = ["publicidade", "comunicação"]
        config.max_pages = 12
        database.commit()

        payload = monitor_payload(config)

        assert payload["modalidades"] == [6, 8]
        assert payload["uf"] == "ES"
        assert payload["palavras_chave"] == ["publicidade", "comunicação"]
        assert payload["max_paginas"] == 12


def test_queue_monitor_prevents_duplicate_running_jobs():
    with make_session() as database:
        first = queue_monitor_job(database)
        second = queue_monitor_job(database)
        assert first.id == second.id
        assert first.job_type == "daily_monitor"
