from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from html import unescape
from typing import Any
from urllib.parse import urljoin

import httpx
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Edital

AMUNES_LANDING_URL = "https://www.amunes.org.br/pagina/36/licitamunes"
LICITAR_PUBLIC_URL = "https://licitar.digital/"


def _clean(value: Any) -> str | None:
    if value is None:
        return None
    text = re.sub(r"\s+", " ", unescape(str(value))).strip()
    return text or None


def _parse_date(value: Any) -> datetime | None:
    if not value:
        return None
    text = str(value).strip().replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(text)
        return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)
    except ValueError:
        return None


def _walk_json(value: Any):
    if isinstance(value, dict):
        yield value
        for child in value.values():
            yield from _walk_json(child)
    elif isinstance(value, list):
        for child in value:
            yield from _walk_json(child)


def _candidate_from_dict(item: dict[str, Any], base_url: str) -> dict[str, Any] | None:
    title = _clean(item.get("titulo") or item.get("title") or item.get("objeto") or item.get("object"))
    organization = _clean(item.get("orgao") or item.get("organization") or item.get("entidade") or item.get("comprador"))
    number = _clean(item.get("numero") or item.get("number") or item.get("processo") or item.get("processNumber"))
    url = _clean(item.get("url") or item.get("link") or item.get("href"))
    if not title or not (organization or number or url):
        return None
    external = _clean(item.get("id") or item.get("codigo") or number or url)
    return {
        "external_id": external,
        "title": title[:500],
        "object_text": _clean(item.get("objeto") or item.get("description") or item.get("descricao")) or title,
        "organization": organization,
        "municipality": _clean(item.get("municipio") or item.get("city")),
        "uf": (_clean(item.get("uf") or item.get("estado")) or "ES")[:2].upper(),
        "modality_name": _clean(item.get("modalidade") or item.get("modality")),
        "status_name": _clean(item.get("situacao") or item.get("status")),
        "process_number": number,
        "proposal_end": _parse_date(item.get("dataFim") or item.get("proposalEnd") or item.get("fimRecebimentoPropostas")),
        "publication_date": _parse_date(item.get("dataPublicacao") or item.get("publicationDate")),
        "source_url": urljoin(base_url, url) if url else base_url,
        "raw_metadata": item,
    }


def discover_public_records(timeout: float = 25.0) -> tuple[list[dict[str, Any]], list[str]]:
    """Busca registros públicos expostos pelo portal AMUNES/LicitaMunes.

    O portal pode alterar a camada pública. O conector procura JSON estruturado e
    cards/links de processos sem depender de login. Quando não houver dados
    estruturados, retorna diagnóstico em vez de criar oportunidades artificiais.
    """
    errors: list[str] = []
    records: list[dict[str, Any]] = []
    headers = {"User-Agent": "HORUS-Connective/0.12 (+monitoramento-publico)"}
    with httpx.Client(timeout=timeout, follow_redirects=True, headers=headers) as client:
        for url in (AMUNES_LANDING_URL, LICITAR_PUBLIC_URL):
            try:
                response = client.get(url)
                response.raise_for_status()
            except Exception as exc:  # noqa: BLE001
                errors.append(f"{url}: {exc}")
                continue
            html = response.text
            scripts = re.findall(r"<script[^>]*>(.*?)</script>", html, flags=re.I | re.S)
            for script in scripts:
                body = script.strip()
                if not body or body[0] not in "[{":
                    continue
                try:
                    payload = json.loads(body)
                except Exception:
                    continue
                for item in _walk_json(payload):
                    candidate = _candidate_from_dict(item, str(response.url))
                    if candidate:
                        records.append(candidate)
            for href, label in re.findall(r'<a[^>]+href=["\']([^"\']+)["\'][^>]*>(.*?)</a>', html, flags=re.I | re.S):
                clean_label = _clean(re.sub(r"<[^>]+>", " ", label))
                if clean_label and re.search(r"licita|processo|concorr|pregao|edital", clean_label, re.I):
                    records.append({
                        "external_id": href,
                        "title": clean_label[:500],
                        "object_text": clean_label,
                        "organization": "AMUNES / Município capixaba",
                        "municipality": None,
                        "uf": "ES",
                        "modality_name": None,
                        "status_name": "Situação a confirmar na fonte",
                        "process_number": None,
                        "proposal_end": None,
                        "publication_date": None,
                        "source_url": urljoin(str(response.url), href),
                        "raw_metadata": {"href": href, "label": clean_label},
                    })
    unique: dict[str, dict[str, Any]] = {}
    for item in records:
        key = str(item.get("external_id") or item.get("source_url") or item.get("title"))
        unique[key] = item
    return list(unique.values()), errors


def _matches_exact_phrases(record: dict[str, Any], exact_phrases: list[str]) -> bool:
    if not exact_phrases:
        return True
    def norm(value: Any) -> str:
        import unicodedata
        text = unicodedata.normalize("NFKD", str(value or "").casefold())
        return "".join(char for char in text if not unicodedata.combining(char))
    haystack = norm(" ".join(str(record.get(key) or "") for key in ("title", "object_text", "organization", "modality_name")))
    return any(norm(phrase) in haystack for phrase in exact_phrases if str(phrase).strip())


def sync_amunes(database: Session, exact_phrases: list[str] | None = None) -> dict[str, Any]:
    records, errors = discover_public_records()
    records = [record for record in records if _matches_exact_phrases(record, list(exact_phrases or []))]
    created = updated = unchanged = 0
    ids: list[str] = []
    for raw in records:
        external_id = str(raw.get("external_id") or raw.get("source_url") or "")[:240]
        source_key = f"amunes:{external_id}"
        edital = database.scalar(select(Edital).where(Edital.pncp_id == source_key))
        mapped = {
            "pncp_id": source_key,
            "source": "amunes_licitamunes",
            "title": raw["title"],
            "object_text": raw.get("object_text"),
            "process_number": raw.get("process_number"),
            "organization": raw.get("organization"),
            "municipality": raw.get("municipality"),
            "uf": raw.get("uf") or "ES",
            "modality_name": raw.get("modality_name"),
            "status_name": raw.get("status_name"),
            "proposal_end": raw.get("proposal_end"),
            "publication_date": raw.get("publication_date"),
            "source_url": raw.get("source_url"),
            "raw_metadata": raw.get("raw_metadata") or raw,
            "indexing_status": "metadata_only",
        }
        if edital is None:
            edital = Edital(**mapped)
            database.add(edital)
            database.flush()
            created += 1
        else:
            changed = any(getattr(edital, key) != value for key, value in mapped.items())
            if changed:
                for key, value in mapped.items():
                    setattr(edital, key, value)
                updated += 1
            else:
                unchanged += 1
        ids.append(edital.id)
    database.commit()
    return {"source": "amunes_licitamunes", "records_found": len(records), "created": created, "updated": updated, "unchanged": unchanged, "edital_ids": ids, "errors": errors}
