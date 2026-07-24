from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

def test_interaction_css_is_loaded_last():
    css = (ROOT / "app/static/css/main.css").read_text(encoding="utf-8")
    assert css.strip().endswith("@import url('/static/css/interaction-fix.css?v=0.16.0-desktop-beta');")

def test_search_controls_are_explicitly_interactive():
    css = (ROOT / "app/static/css/interaction-fix.css").read_text(encoding="utf-8")
    assert "pointer-events:auto!important" in css
    assert ".modal-overlay.hidden" in css
    assert "pointer-events:none!important" in css

def test_all_brazilian_states_are_available():
    js = (ROOT / "app/static/js/app.js").read_text(encoding="utf-8")
    for uf in ["AC","AL","AP","AM","BA","CE","DF","ES","GO","MA","MT","MS","MG","PA","PB","PR","PE","PI","RJ","RN","RS","RO","RR","SC","SP","SE","TO"]:
        assert f'"{uf}"' in js
    assert "populateUfs(cache);" in js
    assert "populatePipelineUfs(pipelineCache);" in js

def test_desktop_window_is_focusable_and_not_easy_drag():
    launcher = (ROOT / "desktop/launcher.py").read_text(encoding="utf-8")
    assert "focus=True" in launcher
    assert "easy_drag=False" in launcher
    assert "draggable=False" in launcher

def test_search_inputs_are_not_readonly():
    for relative in ["app/templates/views/base.html", "app/templates/views/radar.html", "app/templates/views/pipeline.html"]:
        html = (ROOT / relative).read_text(encoding="utf-8")
        assert "readonly" not in html.lower()
        assert 'tabindex="0"' in html
