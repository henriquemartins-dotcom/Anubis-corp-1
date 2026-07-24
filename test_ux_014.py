from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

def test_base_cards_open_details_and_search_is_live():
    js = (ROOT / "app/static/js/app.js").read_text(encoding="utf-8")
    assert 'data-open-edital="${esc(edital.id)}"' in js
    assert '$("editaisSearch").oninput' in js

def test_multisource_search_is_automatic():
    html = (ROOT / "app/templates/views/radar.html").read_text(encoding="utf-8")
    js = (ROOT / "app/static/js/app.js").read_text(encoding="utf-8")
    assert "syncAmunesButton" not in html
    assert 'api("/api/sync/amunes"' in js
    assert "PNCP + AMUNES" in html

def test_sidebar_can_collapse():
    html = (ROOT / "app/templates/components/sidebar.html").read_text(encoding="utf-8")
    css = (ROOT / "app/static/css/layout.css").read_text(encoding="utf-8")
    assert "sidebarCollapseButton" in html
    assert ".sidebar-collapsed .sidebar" in css
