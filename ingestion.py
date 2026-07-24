from __future__ import annotations

from datetime import datetime
from difflib import SequenceMatcher
import time
import unicodedata
from typing import Any

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.models import Chunk, Document, Edital, SyncJob
from app.schemas import SyncPNCPRequest
from app.services.ai import AIProvider
from app.services.chunking import chunk_pages
from app.services.documents import ExtractedPayload, extract_payloads, save_payload, sha256_bytes
from app.services.pncp import PNCPClient, map_publication_record

settings = get_settings()


def _format_date(value: datetime | None) -> str:
    return value.isoformat() if value else "não informado"


def metadata_text(edital: Edital) -> str:
    if edital.estimated_value is None:
        value = "não informado"
    else:
        number = f"{edital.estimated_value:,.2f}"
        value = "R$ " + number.replace(",", "_").replace(".", ",").replace("_", ".")
    return "\n".join(
        [
            f"Título: {edital.title}",
            f"Identificador PNCP: {edital.pncp_id or 'não informado'}",
            f"Órgão: {edital.organization or 'não informado'}",
            f"CNPJ: {edital.cnpj or 'não informado'}",
            f"Município/UF: {edital.municipality or 'não informado'}/{edital.uf or 'não informado'}",
            f"Modalidade: {edital.modality_name or 'não informado'}",
            f"Situação: {edital.status_name or 'não informado'}",
            f"Processo: {edital.process_number or 'não informado'}",
            f"Número da compra: {edital.purchase_number or 'não informado'}",
            f"Objeto: {edital.object_text or 'não informado'}",
            f"Valor total estimado: {value}",
            f"Início das propostas: {_format_date(edital.proposal_start)}",
            f"Encerramento das propostas: {_format_date(edital.proposal_end)}",
            f"Publicação no PNCP: {_format_date(edital.publication_date)}",
            f"Fonte: {edital.source_url or 'não informado'}",
        ]
    )


def upsert_pncp_edital(database: Session, raw_record: dict[str, Any]) -> tuple[Edital, bool, bool]:
    mapped = map_publication_record(raw_record)
    pncp_id = mapped.get("pncp_id")
    edital = database.scalar(select(Edital).where(Edital.pncp_id == pncp_id)) if pncp_id else None
    created = edital is None
    changed = True

    if edital is None:
        edital = Edital(**mapped)
        database.add(edital)
    else:
        changed = edital.raw_metadata != raw_record
        for key, value in mapped.items():
            setattr(edital, key, value)

    database.flush()
    return edital, created, changed


def _replace_document_chunks(
    database: Session,
    document: Document,
    payload: ExtractedPayload,
    ai: AIProvider,
) -> int:
    chunks = chunk_pages(
        payload.pages,
        chunk_size=settings.chunk_size_chars,
        overlap=settings.chunk_overlap_chars,
    )
    database.execute(delete(Chunk).where(Chunk.document_id == document.id))

    if not chunks:
        document.status = "no_text"
        document.error_message = (
            "Nenhum texto pesquisável foi extraído. O arquivo pode ser digitalizado e exigir OCR."
        )
        return 0

    if len(chunks) > settings.max_chunks_per_document:
        raise ValueError(
            f"Documento gerou {len(chunks)} trechos, acima do limite de "
            f"{settings.max_chunks_per_document}. Divida o arquivo ou ajuste a configuração."
        )

    embeddings = ai.embed_texts([chunk.content for chunk in chunks])
    for chunk, embedding in zip(chunks, embeddings, strict=True):
        database.add(
            Chunk(
                edital_id=document.edital_id,
                document_id=document.id,
                page_number=chunk.page_number,
                chunk_index=chunk.chunk_index,
                content=chunk.content,
                embedding=embedding,
            )
        )
    document.status = "indexed"
    document.error_message = None
    return len(chunks)


def index_metadata(database: Session, edital: Edital, ai: AIProvider) -> int:
    external_key = f"metadata:{edital.id}"
    document = database.scalar(select(Document).where(Document.external_key == external_key))
    if document is None:
        document = Document(
            edital_id=edital.id,
            external_key=external_key,
            title="Metadados estruturados do PNCP",
            document_type="Metadados PNCP",
            source_url=edital.source_url,
            mime_type="text/plain",
            status="pending",
        )
        database.add(document)
        database.flush()
    else:
        document.source_url = edital.source_url

    payload = ExtractedPayload(
        filename="metadados-pncp.txt",
        mime_type="text/plain",
        raw_bytes=metadata_text(edital).encode("utf-8"),
        pages=[(None, metadata_text(edital))],
    )
    return _replace_document_chunks(database, document, payload, ai)


def _persist_payload_document(
    database: Session,
    edital: Edital,
    payload: ExtractedPayload,
    external_key: str,
    title: str,
    document_type: str | None,
    source_url: str | None,
    ai: AIProvider,
) -> tuple[Document, int, bool]:
    existing = database.scalar(select(Document).where(Document.external_key == external_key))
    digest = sha256_bytes(payload.raw_bytes)
    if existing and existing.sha256 == digest and existing.status == "indexed":
        return existing, 0, False

    document = existing or Document(
        edital_id=edital.id,
        external_key=external_key,
        title=title,
        document_type=document_type,
        source_url=source_url,
    )
    if existing is None:
        database.add(document)
        database.flush()

    document.title = title
    document.document_type = document_type
    document.source_url = source_url
    document.mime_type = payload.mime_type
    document.sha256 = digest
    document.status = "processing"
    document.error_message = None
    database.flush()

    path = save_payload(edital.id, document.id, payload)
    document.local_path = str(path)
    chunks = _replace_document_chunks(database, document, payload, ai)
    return document, chunks, True


def ingest_uploaded_file(
    database: Session,
    title: str,
    data: bytes,
    filename: str,
    mime_type: str | None,
) -> tuple[Edital, int, int]:
    if len(data) > settings.max_upload_bytes:
        raise ValueError(f"Arquivo excede o limite de {settings.max_upload_mb} MB")

    ai = AIProvider()
    edital = Edital(
        source="upload",
        title=title.strip() or filename,
        object_text="Documento enviado diretamente pelo usuário",
        indexing_status="processing",
    )
    database.add(edital)
    database.flush()

    payloads = extract_payloads(data, filename, mime_type)
    documents_indexed = 0
    chunks_created = 0
    for index, payload in enumerate(payloads, start=1):
        external_key = f"upload:{edital.id}:{index}:{sha256_bytes(payload.raw_bytes)}"
        _, chunks, processed = _persist_payload_document(
            database=database,
            edital=edital,
            payload=payload,
            external_key=external_key,
            title=payload.filename,
            document_type="Documento enviado",
            source_url=None,
            ai=ai,
        )
        if processed:
            documents_indexed += 1
            chunks_created += chunks

    edital.indexing_status = "indexed" if chunks_created else "needs_ocr"
    database.commit()
    database.refresh(edital)
    return edital, documents_indexed, chunks_created



def ingest_file_into_edital(
    database: Session,
    edital: Edital,
    data: bytes,
    filename: str,
    mime_type: str | None,
    document_type: str = "Documento da concorrência",
) -> tuple[list[Document], int]:
    """Anexa e indexa um ou mais documentos em um edital existente."""
    if len(data) > settings.max_upload_bytes:
        raise ValueError(f"Arquivo excede o limite de {settings.max_upload_mb} MB")
    ai = AIProvider()
    payloads = extract_payloads(data, filename, mime_type)
    saved: list[Document] = []
    chunks_created = 0
    for index, payload in enumerate(payloads, start=1):
        digest = sha256_bytes(payload.raw_bytes)
        external_key = f"workspace:{edital.id}:{digest}"
        document, chunks, _processed = _persist_payload_document(
            database=database, edital=edital, payload=payload, external_key=external_key,
            title=payload.filename, document_type=document_type, source_url=None, ai=ai,
        )
        saved.append(document)
        chunks_created += chunks
    edital.indexing_status = "indexed" if chunks_created or edital.indexing_status == "indexed" else "needs_ocr"
    database.commit()
    for document in saved:
        database.refresh(document)
    return saved, chunks_created

def _normalize_search_text(value: str) -> str:
    normalized = unicodedata.normalize("NFKD", value.casefold())
    return "".join(char for char in normalized if not unicodedata.combining(char))


def _matches_exact_phrases(record: dict[str, Any], exact_phrases: list[str]) -> bool:
    if not exact_phrases:
        return True
    haystack = _normalize_search_text(
        " ".join(str(record.get(key) or "") for key in (
            "objetoCompra", "informacaoComplementar", "processo", "numeroCompra", "modalidadeNome"
        ))
    )
    return any(_normalize_search_text(phrase) in haystack for phrase in exact_phrases if phrase.strip())


def _matches_keywords(record: dict[str, Any], keywords: list[str]) -> bool:
    if not keywords:
        return True
    haystack = _normalize_search_text(
        " ".join(
            str(record.get(key) or "")
            for key in (
                "objetoCompra",
                "informacaoComplementar",
                "processo",
                "numeroCompra",
                "modalidadeNome",
            )
        )
    )
    words = set(haystack.replace("/", " ").replace("-", " ").split())
    for keyword in keywords:
        normalized_keyword = _normalize_search_text(keyword)
        if normalized_keyword in haystack:
            return True
        keyword_words = normalized_keyword.split()
        if keyword_words and all(
            any(SequenceMatcher(None, token, word).ratio() >= 0.84 for word in words)
            for token in keyword_words
        ):
            return True
    return False


def run_pncp_sync_job(job_id: str, payload: dict[str, Any]) -> None:
    from app.db import SessionLocal

    request = SyncPNCPRequest.model_validate(payload)
    database = SessionLocal()
    job = database.get(SyncJob, job_id)
    if job is None:
        database.close()
        return

    stats: dict[str, Any] = {
        "created": 0,
        "updated": 0,
        "created_edital_ids": [],
        "updated_edital_ids": [],
        "unchanged": 0,
        "documents_indexed": 0,
        "chunks_created": 0,
        "skipped_by_keyword": 0,
        "duplicates_ignored": 0,
        "records_found": 0,
        "records_processed": 0,
        "errors": [],
        "temporary_failures": 0,
        "retry_attempts": 0,
        "failed_queries": [],
        "progress": {
            "phase": "queued",
            "percent": 0,
            "message": "Aguardando início da sincronização",
        },
    }
    seen_pncp_ids: set[str] = set()
    last_progress_commit = 0.0

    def is_cancel_requested() -> bool:
        database.expire_all()
        current = database.get(SyncJob, job_id)
        return bool(current and current.status in {"cancelling", "cancelled"})

    def save_progress(info: dict[str, Any], *, force: bool = False) -> None:
        nonlocal last_progress_commit
        now = time.monotonic()
        if not force and now - last_progress_commit < settings.pncp_progress_commit_seconds:
            return
        current = database.get(SyncJob, job_id)
        if current is None:
            return
        completed = int(info.get("completed_steps") or 0)
        total = max(int(info.get("total_steps") or 1), 1)
        percent = min(100, round((completed / total) * 100))
        window_start = info.get("window_start")
        window_end = info.get("window_end")
        message = "Consultando o PNCP"
        if window_start and window_end:
            message = (
                f"Período {window_start} a {window_end} · "
                f"modalidade {info.get('modality')} · página {info.get('page')}"
            )
        stats["progress"] = {
            **info,
            "percent": percent,
            "message": message,
            "records_found": stats["records_found"],
            "records_processed": stats["records_processed"],
        }
        current.processed = completed
        current.total = total
        current.result = stats
        database.commit()
        last_progress_commit = now

    def save_retry(info: dict[str, Any]) -> None:
        stats["retry_attempts"] += 1
        current = database.get(SyncJob, job_id)
        if current is None:
            return
        delay = info.get("retry_in_seconds", 0)
        stats["progress"] = {
            **(stats.get("progress") or {}),
            **info,
            "phase": "retrying",
            "message": (
                f"PNCP temporariamente indisponível. Nova tentativa em {delay:g}s "
                f"({info.get('attempt', 0)}/{info.get('max_attempts', 0) - 1})"
            ),
        }
        current.result = stats
        database.commit()

    def save_query_error(info: dict[str, Any]) -> None:
        stats["temporary_failures"] += 1
        key = (
            info.get("window_start"),
            info.get("window_end"),
            info.get("modality"),
            info.get("page"),
        )
        existing_keys = {
            (
                item.get("window_start"),
                item.get("window_end"),
                item.get("modality"),
                item.get("page"),
            )
            for item in stats["failed_queries"]
        }
        if key not in existing_keys:
            stats["failed_queries"].append(info)
        stats["failed_queries"] = stats["failed_queries"][-200:]
        stats["errors"].append({"kind": "pncp_query", **info})
        stats["errors"] = stats["errors"][-100:]
        current = database.get(SyncJob, job_id)
        if current:
            current.result = stats
            database.commit()

    try:
        job.status = "running"
        job.result = stats
        database.commit()
        ai = AIProvider()

        with PNCPClient() as pncp:
            for raw_record in pncp.iter_publications(
                request,
                progress_callback=save_progress,
                cancel_callback=is_cancel_requested,
                error_callback=save_query_error,
                retry_callback=save_retry,
            ):
                if is_cancel_requested():
                    break

                stats["records_found"] += 1
                pncp_id = str(raw_record.get("numeroControlePNCP") or "")
                if pncp_id and pncp_id in seen_pncp_ids:
                    stats["duplicates_ignored"] += 1
                    continue
                if pncp_id:
                    seen_pncp_ids.add(pncp_id)

                if not _matches_exact_phrases(raw_record, request.exact_phrases):
                    stats["skipped_by_keyword"] += 1
                    continue
                if not _matches_keywords(raw_record, request.palavras_chave):
                    stats["skipped_by_keyword"] += 1
                    continue

                try:
                    edital, created, changed = upsert_pncp_edital(database, raw_record)
                    if created:
                        stats["created"] += 1
                        if len(stats["created_edital_ids"]) < 500:
                            stats["created_edital_ids"].append(edital.id)
                    elif changed:
                        stats["updated"] += 1
                        if len(stats["updated_edital_ids"]) < 500:
                            stats["updated_edital_ids"].append(edital.id)
                    else:
                        stats["unchanged"] += 1

                    metadata_key = f"metadata:{edital.id}"
                    metadata_document = database.scalar(
                        select(Document).where(Document.external_key == metadata_key)
                    )
                    if created or changed or metadata_document is None or metadata_document.status != "indexed":
                        stats["chunks_created"] += index_metadata(database, edital, ai)

                    document_chunks = 0
                    indexed_documents = 0
                    if (
                        request.baixar_documentos
                        and edital.cnpj
                        and edital.year is not None
                        and edital.sequence is not None
                    ):
                        documents = pncp.list_documents(edital.cnpj, edital.year, edital.sequence)
                        for document_meta in documents:
                            if is_cancel_requested():
                                break
                            if not document_meta.get("statusAtivo", True):
                                continue
                            current_document_count = 0
                            current_chunk_count = 0
                            try:
                                with database.begin_nested():
                                    sequence = int(document_meta["sequencialDocumento"])
                                    base_key = f"pncp:{edital.cnpj}:{edital.year}:{edital.sequence}:{sequence}"
                                    already = database.scalar(
                                        select(Document).where(Document.external_key == base_key)
                                    )
                                    if already and already.status == "indexed":
                                        continue

                                    data, filename, mime_type, canonical_url = pncp.download_document(
                                        document_meta, edital.cnpj, edital.year, edital.sequence
                                    )
                                    extracted = extract_payloads(data, filename, mime_type)
                                    for child_index, extracted_payload in enumerate(extracted, start=1):
                                        external_key = base_key if len(extracted) == 1 else f"{base_key}:{child_index}"
                                        _, chunks, processed = _persist_payload_document(
                                            database=database,
                                            edital=edital,
                                            payload=extracted_payload,
                                            external_key=external_key,
                                            title=extracted_payload.filename,
                                            document_type=document_meta.get("tipoDocumentoDescricao")
                                            or document_meta.get("tipoDocumentoNome"),
                                            source_url=canonical_url,
                                            ai=ai,
                                        )
                                        if processed:
                                            current_document_count += 1
                                            current_chunk_count += chunks
                                indexed_documents += current_document_count
                                document_chunks += current_chunk_count
                            except Exception as document_error:  # noqa: BLE001
                                stats["errors"].append(
                                    {
                                        "kind": "document",
                                        "pncp_id": pncp_id,
                                        "document": document_meta.get("titulo")
                                        or document_meta.get("sequencialDocumento"),
                                        "error": str(document_error)[:500],
                                    }
                                )
                                stats["errors"] = stats["errors"][-50:]

                    stats["documents_indexed"] += indexed_documents
                    stats["chunks_created"] += document_chunks
                    actual_statuses = list(
                        database.scalars(
                            select(Document.status).where(
                                Document.edital_id == edital.id,
                                Document.external_key.not_like("metadata:%"),
                            )
                        ).all()
                    )
                    if "indexed" in actual_statuses:
                        edital.indexing_status = "indexed"
                    elif "no_text" in actual_statuses:
                        edital.indexing_status = "needs_ocr"
                    else:
                        edital.indexing_status = "metadata_only"
                    stats["records_processed"] += 1
                    database.commit()
                except Exception as exc:  # noqa: BLE001
                    database.rollback()
                    stats["errors"].append({"pncp_id": pncp_id, "error": str(exc)[:500]})
                    stats["errors"] = stats["errors"][-50:]
                    stats["records_processed"] += 1

        job = database.get(SyncJob, job_id)
        if job:
            if job.status in {"cancelling", "cancelled"}:
                job.status = "cancelled"
                stats["progress"] = {
                    **(stats.get("progress") or {}),
                    "phase": "cancelled",
                    "message": "Sincronização cancelada pelo usuário",
                }
            else:
                if stats["failed_queries"]:
                    job.status = "completed_with_warnings"
                    stats["progress"] = {
                        **(stats.get("progress") or {}),
                        "phase": "completed_with_warnings",
                        "percent": 100,
                        "message": (
                            "Sincronização concluída com pendências temporárias do PNCP. "
                            "Use Retomar falhas para tentar novamente."
                        ),
                    }
                else:
                    job.status = "completed"
                    stats["progress"] = {
                        **(stats.get("progress") or {}),
                        "phase": "completed",
                        "percent": 100,
                        "message": "Sincronização concluída",
                    }
                job.processed = job.total or job.processed
            job.result = stats
            database.commit()
    except Exception as exc:  # noqa: BLE001
        database.rollback()
        job = database.get(SyncJob, job_id)
        if job:
            job.status = "failed"
            job.error_message = str(exc)[:2000]
            stats["progress"] = {
                **(stats.get("progress") or {}),
                "phase": "failed",
                "message": "A sincronização encontrou um erro",
            }
            job.result = stats
            database.commit()
    finally:
        database.close()

