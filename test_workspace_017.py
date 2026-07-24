from pathlib import Path


def test_workspace_tabs_and_upload_ui():
    html = Path('app/templates/components/checklist_modal.html').read_text(encoding='utf-8')
    js = Path('app/static/js/app.js').read_text(encoding='utf-8')
    css = Path('app/static/css/checklist.css').read_text(encoding='utf-8')
    assert 'data-checklist-panel="documentos"' in html
    assert 'id="workspaceDropzone"' in html
    assert 'uploadWorkspaceFiles' in js
    assert 'activateChecklistTab' in js
    assert '.checklist-workspace-list{min-height:0;flex:1 1 auto' in css


def test_workspace_document_api_exists():
    source = Path('app/main.py').read_text(encoding='utf-8')
    ingestion = Path('app/services/ingestion.py').read_text(encoding='utf-8')
    assert '@app.post("/api/editais/{edital_id}/documents")' in source
    assert '@app.get("/api/editais/{edital_id}/documents")' in source
    assert 'def ingest_file_into_edital' in ingestion
