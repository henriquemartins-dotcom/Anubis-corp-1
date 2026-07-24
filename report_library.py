from __future__ import annotations

import base64
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def reports_root(data_dir: Path) -> Path:
    root = (Path(data_dir) / "reports").resolve()
    root.mkdir(parents=True, exist_ok=True)
    return root


def _encode_relative_path(relative_path: Path) -> str:
    payload = relative_path.as_posix().encode("utf-8")
    return base64.urlsafe_b64encode(payload).decode("ascii").rstrip("=")


def _decode_relative_path(report_id: str) -> Path:
    try:
        padding = "=" * (-len(report_id) % 4)
        decoded = base64.urlsafe_b64decode(report_id + padding).decode("utf-8")
    except (ValueError, UnicodeDecodeError) as exc:
        raise ValueError("Identificador de relatório inválido") from exc
    relative = Path(decoded)
    if relative.is_absolute() or ".." in relative.parts:
        raise ValueError("Identificador de relatório inválido")
    return relative


def classify_report(path: Path, root: Path) -> str:
    relative = path.relative_to(root)
    parts = {part.lower() for part in relative.parts[:-1]}
    name = path.name.lower()
    if "checklists" in parts or name.startswith("checklist_"):
        return "Checklist operacional"
    if "monitoramento" in parts or "monitor" in name:
        return "Monitoramento diário"
    if name.startswith("relatorio_concorrencias"):
        return "Relatório de concorrências"
    return "Relatório PDF"


def list_saved_reports(data_dir: Path) -> list[dict[str, Any]]:
    root = reports_root(data_dir)
    items: list[dict[str, Any]] = []
    for path in root.rglob("*.pdf"):
        if not path.is_file():
            continue
        try:
            stat = path.stat()
            relative = path.resolve().relative_to(root)
        except (OSError, ValueError):
            continue
        modified = datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc)
        items.append(
            {
                "id": _encode_relative_path(relative),
                "name": path.name,
                "category": classify_report(path, root),
                "relative_path": relative.as_posix(),
                "size_bytes": stat.st_size,
                "modified_at": modified.isoformat(),
            }
        )
    items.sort(key=lambda item: item["modified_at"], reverse=True)
    return items


def resolve_saved_report(data_dir: Path, report_id: str) -> Path:
    root = reports_root(data_dir)
    relative = _decode_relative_path(report_id)
    path = (root / relative).resolve()
    if root != path.parent and root not in path.parents:
        raise ValueError("Relatório fora da pasta permitida")
    if path.suffix.lower() != ".pdf" or not path.is_file():
        raise FileNotFoundError("Relatório não encontrado")
    return path


def delete_saved_report(data_dir: Path, report_id: str) -> Path:
    path = resolve_saved_report(data_dir, report_id)
    path.unlink()
    parent = path.parent
    root = reports_root(data_dir)
    while parent != root:
        try:
            parent.rmdir()
        except OSError:
            break
        parent = parent.parent
    return path
