from __future__ import annotations

import re
import time
from collections.abc import Iterator
from datetime import date, datetime, timedelta
from email.message import Message
from pathlib import Path
from zoneinfo import ZoneInfo
from typing import Any
from urllib.parse import urlparse

import httpx
from app.config import get_settings
from app.schemas import SyncPNCPRequest
from app.services.utils import safe_filename

settings = get_settings()

MODALIDADES: dict[int, str] = {
    1: "Leilão - Eletrônico",
    2: "Diálogo Competitivo",
    3: "Concurso",
    4: "Concorrência - Eletrônica",
    5: "Concorrência - Presencial",
    6: "Pregão - Eletrônico",
    7: "Pregão - Presencial",
    8: "Dispensa",
    9: "Inexigibilidade",
    10: "Manifestação de Interesse",
    11: "Pré-qualificação",
    12: "Credenciamento",
    13: "Leilão - Presencial",
    14: "Inaplicabilidade da Licitação",
    15: "Chamada Pública",
}


def is_allowed_pncp_url(value: str) -> bool:
    parsed = urlparse(value)
    hostname = (parsed.hostname or "").lower()
    return parsed.scheme == "https" and (hostname == "pncp.gov.br" or hostname.endswith(".pncp.gov.br"))


class PNCPTemporaryError(RuntimeError):
    pass


def parse_datetime(value: Any) -> datetime | None:
    if not value or not isinstance(value, str):
        return None
    normalized = value.strip().replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(normalized)
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=ZoneInfo("America/Sao_Paulo"))
        return parsed
    except ValueError:
        return None


def extract_cnpj(record: dict[str, Any]) -> str | None:
    organization = record.get("orgaoEntidade") or {}
    candidates = [organization.get("cnpj"), record.get("cnpj"), record.get("numeroControlePNCP")]
    for candidate in candidates:
        digits = re.sub(r"\D", "", str(candidate or ""))
        if len(digits) >= 14:
            return digits[:14]
    return None


def map_publication_record(record: dict[str, Any]) -> dict[str, Any]:
    organization = record.get("orgaoEntidade") or {}
    unit = record.get("unidadeOrgao") or {}
    cnpj = extract_cnpj(record)
    year = record.get("anoCompra")
    sequence = record.get("sequencialCompra")

    detail_url = None
    if cnpj and year is not None and sequence is not None:
        detail_url = (
            f"{settings.pncp_consulta_base_url}/v1/orgaos/{cnpj}/compras/{int(year)}/{int(sequence)}"
        )

    title_parts = [record.get("modalidadeNome"), record.get("numeroCompra") or record.get("processo")]
    title = " - ".join(str(value).strip() for value in title_parts if value)
    if not title:
        title = str(record.get("numeroControlePNCP") or "Edital PNCP")

    estimated = record.get("valorTotalEstimado")
    try:
        estimated_value = float(estimated) if estimated is not None else None
    except (TypeError, ValueError):
        estimated_value = None

    return {
        "pncp_id": record.get("numeroControlePNCP"),
        "source": "pncp",
        "title": title[:500],
        "object_text": record.get("objetoCompra"),
        "process_number": record.get("processo"),
        "purchase_number": record.get("numeroCompra"),
        "cnpj": cnpj,
        "year": int(year) if year is not None else None,
        "sequence": int(sequence) if sequence is not None else None,
        "organization": organization.get("razaoSocial") or organization.get("nome") or record.get("orgaoNome"),
        "municipality": unit.get("municipioNome") or record.get("municipioNome"),
        "uf": unit.get("ufSigla") or record.get("ufSigla") or record.get("uf"),
        "modality_id": record.get("modalidadeId"),
        "modality_name": record.get("modalidadeNome"),
        "status_name": record.get("situacaoCompraNome"),
        "estimated_value": estimated_value,
        "proposal_start": parse_datetime(record.get("dataAberturaProposta")),
        "proposal_end": parse_datetime(record.get("dataEncerramentoProposta")),
        "publication_date": parse_datetime(record.get("dataPublicacaoPncp")),
        "source_url": record.get("linkSistemaOrigem") or detail_url,
        "raw_metadata": record,
    }


def document_filename(document: dict[str, Any], headers: httpx.Headers | None = None) -> str:
    if headers:
        disposition = headers.get("content-disposition")
        if disposition:
            message = Message()
            message["content-disposition"] = disposition
            filename = message.get_filename()
            if filename:
                return safe_filename(filename)
    title = str(document.get("titulo") or f"documento-{document.get('sequencialDocumento', 'pncp')}")
    if not Path(title).suffix:
        title += ".pdf"
    return safe_filename(title)


def iter_date_windows(start: date, end: date, window_days: int) -> Iterator[tuple[date, date]]:
    """Divide períodos longos em janelas inclusivas aceitas pela API do PNCP."""
    if window_days < 1:
        raise ValueError("window_days deve ser maior que zero")
    current = start
    while current <= end:
        window_end = min(current + timedelta(days=window_days - 1), end)
        yield current, window_end
        current = window_end + timedelta(days=1)


class PNCPClient:
    def __init__(self) -> None:
        self.client = httpx.Client(
            timeout=settings.pncp_timeout_seconds,
            follow_redirects=True,
            headers={"User-Agent": "DanzaLicitaIA/4.1", "Accept": "application/json, */*"},
        )
        self._last_request_at = 0.0

    def close(self) -> None:
        self.client.close()

    def __enter__(self) -> "PNCPClient":
        return self

    def __exit__(self, exc_type: Any, exc: Any, traceback: Any) -> None:
        self.close()

    def _throttle(self) -> None:
        delay = max(float(settings.pncp_request_delay_seconds), 0.0)
        elapsed = time.monotonic() - self._last_request_at
        if self._last_request_at and elapsed < delay:
            time.sleep(delay - elapsed)

    def _get(
        self,
        url: str,
        params: dict[str, Any] | None = None,
        *,
        retry_callback: Any | None = None,
        context: dict[str, Any] | None = None,
    ) -> httpx.Response:
        last_error: Exception | None = None
        attempts = max(int(settings.pncp_max_retries), 1)
        retryable_statuses = {408, 425, 429, 500, 502, 503, 504}

        for attempt in range(1, attempts + 1):
            try:
                self._throttle()
                response = self.client.get(url, params=params)
                self._last_request_at = time.monotonic()
                if response.status_code == 204:
                    return response
                if response.status_code in retryable_statuses:
                    raise PNCPTemporaryError(
                        f"PNCP indisponível temporariamente: HTTP {response.status_code}"
                    )
                response.raise_for_status()
                return response
            except (httpx.TransportError, PNCPTemporaryError) as exc:
                last_error = exc
                if attempt >= attempts:
                    raise
                delay = min(
                    float(settings.pncp_retry_base_delay_seconds) * (2 ** (attempt - 1)),
                    float(settings.pncp_retry_max_delay_seconds),
                )
                if retry_callback:
                    retry_callback(
                        {
                            **(context or {}),
                            "attempt": attempt,
                            "max_attempts": attempts,
                            "retry_in_seconds": delay,
                            "error": str(exc),
                        }
                    )
                time.sleep(delay)

        raise RuntimeError(f"Falha ao consultar o PNCP: {last_error}")

    def iter_publications(
        self,
        request: SyncPNCPRequest,
        progress_callback: Any | None = None,
        cancel_callback: Any | None = None,
        error_callback: Any | None = None,
        retry_callback: Any | None = None,
    ) -> Iterator[dict[str, Any]]:
        endpoint = f"{settings.pncp_consulta_base_url}/v1/contratacoes/publicacao"

        if request.retry_queries:
            query_groups = [
                {
                    "window_start": date.fromisoformat(item["window_start"]),
                    "window_end": date.fromisoformat(item["window_end"]),
                    "modality": int(item["modality"]),
                    "start_page": int(item.get("page", 1)),
                }
                for item in request.retry_queries
            ]
        else:
            windows = list(
                iter_date_windows(
                    request.data_inicial,
                    request.data_final,
                    settings.pncp_api_batch_days,
                )
            )
            query_groups = [
                {
                    "window_start": window_start,
                    "window_end": window_end,
                    "modality": modality,
                    "start_page": 1,
                }
                for window_start, window_end in windows
                for modality in request.modalidades
            ]

        total_steps = max(
            sum(request.max_paginas - int(item["start_page"]) + 1 for item in query_groups),
            1,
        )
        completed_steps = 0

        for group_index, group in enumerate(query_groups, start=1):
            window_start = group["window_start"]
            window_end = group["window_end"]
            modality = int(group["modality"])
            start_page = int(group["start_page"])
            page = start_page

            for page in range(start_page, request.max_paginas + 1):
                if cancel_callback and cancel_callback():
                    return

                context = {
                    "phase": "consulting",
                    "group_index": group_index,
                    "group_total": len(query_groups),
                    "window_start": window_start.isoformat(),
                    "window_end": window_end.isoformat(),
                    "modality": modality,
                    "page": page,
                    "completed_steps": completed_steps,
                    "total_steps": total_steps,
                }
                if progress_callback:
                    progress_callback(context)

                params: dict[str, Any] = {
                    "dataInicial": window_start.strftime("%Y%m%d"),
                    "dataFinal": window_end.strftime("%Y%m%d"),
                    "codigoModalidadeContratacao": modality,
                    "pagina": page,
                    "tamanhoPagina": request.tamanho_pagina,
                }
                if request.uf:
                    params["uf"] = request.uf

                try:
                    response = self._get(
                        endpoint,
                        params=params,
                        retry_callback=retry_callback,
                        context=context,
                    )
                except (httpx.TransportError, PNCPTemporaryError) as exc:
                    failed = {
                        "window_start": window_start.isoformat(),
                        "window_end": window_end.isoformat(),
                        "modality": modality,
                        "page": page,
                        "error": str(exc),
                    }
                    if error_callback:
                        error_callback(failed)
                    # O restante das páginas desta modalidade fica pendente para retomada.
                    completed_steps += request.max_paginas - page + 1
                    if progress_callback:
                        progress_callback(
                            {
                                **context,
                                "phase": "query_failed",
                                "completed_steps": completed_steps,
                                "error": str(exc),
                            },
                            force=True,
                        )
                    break

                completed_steps += 1
                if response.status_code == 204:
                    completed_steps += request.max_paginas - page
                    break

                payload = response.json()
                rows = payload.get("data") or payload.get("items") or []
                if not rows:
                    completed_steps += request.max_paginas - page
                    break

                for row in rows:
                    yield row

                total_pages = payload.get("totalPaginas") or payload.get("total_pages")
                if total_pages is not None and page >= int(total_pages):
                    completed_steps += request.max_paginas - page
                    break
                if len(rows) < request.tamanho_pagina:
                    completed_steps += request.max_paginas - page
                    break

        if progress_callback:
            progress_callback(
                {
                    "phase": "finished_queries",
                    "completed_steps": total_steps,
                    "total_steps": total_steps,
                    "group_index": len(query_groups),
                    "group_total": len(query_groups),
                },
                force=True,
            )

    def list_documents(self, cnpj: str, year: int, sequence: int) -> list[dict[str, Any]]:
        url = f"{settings.pncp_files_base_url}/v1/orgaos/{cnpj}/compras/{year}/{sequence}/arquivos/"
        response = self._get(url)
        if response.status_code == 204:
            return []
        payload = response.json()
        return payload if isinstance(payload, list) else payload.get("data", [])

    def canonical_document_url(self, cnpj: str, year: int, sequence: int, document_sequence: int) -> str:
        return (
            f"{settings.pncp_files_base_url}/v1/orgaos/{cnpj}/compras/{year}/{sequence}"
            f"/arquivos/{document_sequence}"
        )

    def download_document(
        self,
        document: dict[str, Any],
        cnpj: str,
        year: int,
        sequence: int,
    ) -> tuple[bytes, str, str, str]:
        document_sequence = int(document["sequencialDocumento"])
        canonical = self.canonical_document_url(cnpj, year, sequence, document_sequence)
        candidates = [canonical, document.get("url"), document.get("uri")]
        last_error: Exception | None = None

        allowed_candidates = [
            str(value)
            for value in dict.fromkeys(value for value in candidates if value)
            if is_allowed_pncp_url(str(value))
        ]
        for candidate in allowed_candidates:
            try:
                response = self._get(str(candidate))
                data = response.content
                if len(data) > settings.max_document_bytes:
                    raise ValueError("Documento excede o limite configurado")
                filename = document_filename(document, response.headers)
                mime_type = response.headers.get("content-type", "application/octet-stream").split(";")[0]
                return data, filename, mime_type, canonical
            except (httpx.HTTPError, httpx.TransportError, PNCPTemporaryError, ValueError) as exc:
                last_error = exc
                continue

        raise RuntimeError(f"Não foi possível baixar o documento PNCP: {last_error}")
