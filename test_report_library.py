from pathlib import Path

import pytest

from app.services.report_library import delete_saved_report, list_saved_reports, resolve_saved_report


def test_report_library_lists_nested_pdfs_and_classifies_them(tmp_path: Path):
    root = tmp_path / "reports"
    checklists = root / "checklists"
    checklists.mkdir(parents=True)
    checklist = checklists / "Checklist_Operacional_ALFRED_Teste.pdf"
    checklist.write_bytes(b"%PDF-checklist")
    competition = root / "Relatorio_Concorrencias_ALFRED_20260721.pdf"
    competition.write_bytes(b"%PDF-report")

    items = list_saved_reports(tmp_path)

    assert len(items) == 2
    by_name = {item["name"]: item for item in items}
    assert by_name[checklist.name]["category"] == "Checklist operacional"
    assert by_name[competition.name]["category"] == "Relatório de concorrências"
    assert resolve_saved_report(tmp_path, by_name[checklist.name]["id"]) == checklist.resolve()


def test_report_library_deletes_only_a_valid_report(tmp_path: Path):
    root = tmp_path / "reports"
    root.mkdir()
    report = root / "Relatorio_Concorrencias_ALFRED.pdf"
    report.write_bytes(b"%PDF")
    item = list_saved_reports(tmp_path)[0]

    deleted = delete_saved_report(tmp_path, item["id"])

    assert deleted.name == report.name
    assert not report.exists()


def test_report_library_rejects_invalid_identifier(tmp_path: Path):
    with pytest.raises((ValueError, FileNotFoundError)):
        resolve_saved_report(tmp_path, "bm90LWEtdmFsaWQtcGRm")
