from pathlib import Path


def test_checklist_has_dedicated_visible_vertical_scrollbar():
    css = Path("app/static/css/checklist.css").read_text(encoding="utf-8")
    assert 'data-checklist-panel="checklist"].active' in css
    assert "overflow-y: scroll" in css
    assert "scrollbar-gutter: stable" in css
    assert "height: 0" in css
    assert ".checklist-workspace-list::-webkit-scrollbar" in css
