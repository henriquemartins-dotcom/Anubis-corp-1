from __future__ import annotations

import unicodedata
from datetime import datetime, timezone

OPEN_STATUS_TERMS = (
    "aberta", "aberto", "publicada", "publicado", "recebendo proposta",
    "em disputa", "em andamento", "em curso", "julgamento", "habilitacao",
    "analise", "suspensa", "suspenso", "reaberta", "reaberto",
)
CLOSED_STATUS_TERMS = (
    "encerrada", "encerrado", "homologada", "homologado", "adjudicada",
    "adjudicado", "revogada", "revogado", "anulada", "anulado",
    "cancelada", "cancelado", "deserta", "deserto", "fracassada", "fracassado",
)


def _normalize(value: str | None) -> str:
    text = unicodedata.normalize("NFKD", (value or "").casefold())
    return "".join(ch for ch in text if not unicodedata.combining(ch))


def classify_opportunity(status_name: str | None, proposal_end: datetime | None) -> str:
    status = _normalize(status_name)
    if any(term in status for term in CLOSED_STATUS_TERMS):
        return "closed"
    if any(term in status for term in OPEN_STATUS_TERMS):
        return "open"
    if proposal_end is not None:
        value = proposal_end
        if value.tzinfo is None:
            value = value.replace(tzinfo=timezone.utc)
        return "open" if value >= datetime.now(timezone.utc) else "closed"
    return "unknown"
