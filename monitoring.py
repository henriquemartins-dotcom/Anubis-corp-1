from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import SessionLocal
from app.models import MonitorConfig, SyncJob
from app.schemas import SyncPNCPRequest
from app.services.ingestion import run_pncp_sync_job
from app.services.amunes import sync_amunes
from app.services.reports import generate_competition_report

MONITOR_ID = "default"


def get_or_create_monitor_config(database: Session) -> MonitorConfig:
    config = database.get(MonitorConfig, MONITOR_ID)
    if config is None:
        config = MonitorConfig(id=MONITOR_ID)
        database.add(config)
        database.commit()
        database.refresh(config)
    return config


def monitor_payload(config: MonitorConfig) -> dict[str, Any]:
    end = date.today()
    start = end - timedelta(days=max(int(config.lookback_days or 1) - 1, 0))
    request = SyncPNCPRequest(
        data_inicial=start,
        data_final=end,
        modalidades=list(config.modalities or [6, 4, 8]),
        uf=config.uf,
        palavras_chave=list(config.keywords or []),
        exact_phrases=list(config.exact_phrases or []) if config.exact_match_enabled else [],
        baixar_documentos=bool(config.download_documents),
        max_paginas=int(config.max_pages or 5),
    )
    return request.model_dump(mode="json")


def queue_monitor_job(database: Session) -> SyncJob:
    config = get_or_create_monitor_config(database)
    running = database.scalar(
        select(SyncJob)
        .where(
            SyncJob.job_type == "daily_monitor",
            SyncJob.status.in_(["queued", "running", "cancelling"]),
        )
        .order_by(SyncJob.created_at.desc())
        .limit(1)
    )
    if running:
        return running
    job = SyncJob(job_type="daily_monitor", payload=monitor_payload(config))
    database.add(job)
    database.commit()
    database.refresh(job)
    return job


def run_daily_monitor_job(job_id: str | None = None, *, require_enabled: bool = False) -> str | None:
    """Executa uma rodada diária e consolida um relatório das novidades.

    Pode ser chamado pelo APScheduler, pelo botão Executar agora ou pelo modo
    `HORUS_CONNECTIVE.exe --monitor-once` registrado no Agendador de Tarefas do Windows.
    """
    with SessionLocal() as database:
        config = get_or_create_monitor_config(database)
        if require_enabled and not config.enabled:
            config.last_status = "paused"
            database.commit()
            return None
        if job_id is None:
            job = queue_monitor_job(database)
            job_id = job.id
        else:
            job = database.get(SyncJob, job_id)
            if job is None:
                return None
        payload = dict(job.payload or {})

    run_pncp_sync_job(job_id, payload)

    amunes_result: dict[str, Any] = {}
    try:
        with SessionLocal() as source_database:
            amunes_result = sync_amunes(source_database, exact_phrases=list(config.exact_phrases or []) if config.exact_match_enabled else [])
    except Exception as exc:  # noqa: BLE001
        amunes_result = {"source": "amunes_licitamunes", "errors": [str(exc)[:500]], "created": 0, "updated": 0, "records_found": 0}

    with SessionLocal() as database:
        config = get_or_create_monitor_config(database)
        job = database.get(SyncJob, job_id)
        if not job:
            return job_id
        result = dict(job.result or {})
        result["amunes"] = amunes_result
        selected_ids = list(dict.fromkeys(
            list(result.get("created_edital_ids") or [])
            + list(result.get("updated_edital_ids") or [])
            + list(amunes_result.get("edital_ids") or [])
        ))
        report_path: str | None = None
        if config.generate_report and selected_ids and job.status in {"completed", "completed_with_warnings"}:
            try:
                path = generate_competition_report(
                    database,
                    selected_ids,
                    title="Relatório Diário de Monitoramento de Concorrências",
                )
                report_path = str(path)
                result["report_path"] = report_path
            except Exception as exc:  # noqa: BLE001
                result["report_error"] = str(exc)[:500]
        result["monitor_completed_at"] = datetime.now(timezone.utc).isoformat()
        result["monitor_selected_count"] = len(selected_ids)
        job.result = result
        config.last_run_at = datetime.now(timezone.utc)
        config.last_status = job.status
        config.last_report_path = report_path
        config.last_summary = {
            "created": int(result.get("created") or 0),
            "updated": int(result.get("updated") or 0),
            "records_found": int(result.get("records_found") or 0) + int(amunes_result.get("records_found") or 0),
            "amunes_created": int(amunes_result.get("created") or 0),
            "amunes_updated": int(amunes_result.get("updated") or 0),
            "errors": len(result.get("errors") or []),
            "report_path": report_path,
        }
        database.commit()
    return job_id
