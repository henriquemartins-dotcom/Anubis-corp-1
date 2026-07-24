from datetime import datetime, timedelta, timezone
from app.services.opportunity_status import classify_opportunity
from app.services.amunes import _candidate_from_dict


def test_status_classification():
    assert classify_opportunity("Homologada", None) == "closed"
    assert classify_opportunity("Recebendo propostas", None) == "open"
    assert classify_opportunity(None, datetime.now(timezone.utc) + timedelta(days=1)) == "open"
    assert classify_opportunity(None, datetime.now(timezone.utc) - timedelta(days=1)) == "closed"


def test_amunes_structured_candidate():
    item = {"titulo":"Concorrência 01/2026", "orgao":"Prefeitura Teste", "id":123, "uf":"ES", "status":"Aberta"}
    result = _candidate_from_dict(item, "https://example.test/")
    assert result and result["title"] == "Concorrência 01/2026"
    assert result["uf"] == "ES"
