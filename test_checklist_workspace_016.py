from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_checklist_is_fullscreen_workspace():
    html = (ROOT / "app/templates/components/checklist_modal.html").read_text(encoding="utf-8")
    css = (ROOT / "app/static/css/checklist.css").read_text(encoding="utf-8")
    assert 'class="checklist-workspace hidden"' in html
    assert "CENTRO DE GERENCIAMENTO DA CONCORRÊNCIA" in html
    assert ".checklist-workspace{position:fixed;inset:0" in css
    assert "checklist-table-head" in html
    assert "checklistSearchInput" in html


def test_release_version_current():
    config = (ROOT / "app/config.py").read_text(encoding="utf-8")
    launcher = (ROOT / "desktop/launcher.py").read_text(encoding="utf-8")
    assert '0.17.2-desktop-beta' in config
    assert 'APP_VERSION = "0.17.2-desktop-beta"' in launcher
