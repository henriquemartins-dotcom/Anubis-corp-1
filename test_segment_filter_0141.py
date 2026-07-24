from app.schemas import SyncPNCPRequest
from app.services.ingestion import _matches_exact_phrases
from app.services.amunes import _matches_exact_phrases as amunes_matches
from datetime import date


def test_exact_segment_phrase_is_accent_insensitive():
    record = {"objetoCompra": "Contratação de agência de publicidade e propaganda para campanhas institucionais"}
    assert _matches_exact_phrases(record, ["agencia de publicidade"])
    assert not _matches_exact_phrases(record, ["construção civil"])


def test_amunes_exact_segment_filter():
    record = {"title": "Concorrência", "object_text": "Serviços de publicidade e propaganda", "organization": "Prefeitura"}
    assert amunes_matches(record, ["publicidade e propaganda"])
    assert not amunes_matches(record, ["material hospitalar"])


def test_sync_request_normalizes_exact_phrases():
    payload = SyncPNCPRequest(data_inicial=date.today(), data_final=date.today(), modalidades=[6], exact_phrases=[" publicidade e propaganda ", "publicidade e propaganda"])
    assert payload.exact_phrases == ["publicidade e propaganda"]


def test_settings_view_and_sidebar_scroll_fix_are_present():
    from pathlib import Path
    root = Path(__file__).resolve().parents[1]
    assert 'id="view-settings"' in (root / "app/templates/views/settings.html").read_text(encoding="utf-8")
    css = (root / "app/static/css/layout.css").read_text(encoding="utf-8")
    assert "scrollbar-width:none" in css
    assert "overflow-x:hidden" in css
