from __future__ import annotations

import math
from collections import defaultdict

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.models import Chunk, Document, Edital
from app.schemas import AskRequest, AskResponse, SourceOut
from app.services.ai import AIProvider

settings = get_settings()


def _cosine_distance(left: list[float] | None, right: list[float]) -> float:
    if not left or not right:
        return 1.0
    size = min(len(left), len(right))
    dot = sum(float(left[index]) * float(right[index]) for index in range(size))
    left_norm = math.sqrt(sum(float(left[index]) ** 2 for index in range(size)))
    right_norm = math.sqrt(sum(float(right[index]) ** 2 for index in range(size)))
    if not left_norm or not right_norm:
        return 1.0
    similarity = max(-1.0, min(1.0, dot / (left_norm * right_norm)))
    return 1.0 - similarity


def _sqlite_rows(
    database: Session,
    request: AskRequest,
    query_embedding: list[float],
) -> list[tuple[Chunk, Document, Edital, float]]:
    statement = (
        select(Chunk, Document, Edital)
        .join(Document, Chunk.document_id == Document.id)
        .join(Edital, Chunk.edital_id == Edital.id)
    )
    if request.edital_ids:
        statement = statement.where(Chunk.edital_id.in_(request.edital_ids))

    rows = database.execute(statement).all()
    ranked = [
        (chunk, document, edital, _cosine_distance(chunk.embedding, query_embedding))
        for chunk, document, edital in rows
    ]
    ranked.sort(key=lambda item: item[3])
    return ranked[: max(request.top_k * 4, 24)]


def _postgres_rows(
    database: Session,
    request: AskRequest,
    query_embedding: list[float],
) -> list[tuple[Chunk, Document, Edital, float]]:
    distance = Chunk.embedding.cosine_distance(query_embedding).label("distance")
    statement = (
        select(Chunk, Document, Edital, distance)
        .join(Document, Chunk.document_id == Document.id)
        .join(Edital, Chunk.edital_id == Edital.id)
    )
    if request.edital_ids:
        statement = statement.where(Chunk.edital_id.in_(request.edital_ids))
    statement = statement.order_by(distance).limit(max(request.top_k * 4, 24))
    return [
        (chunk, document, edital, float(raw_distance))
        for chunk, document, edital, raw_distance in database.execute(statement).all()
    ]


def answer_question(database: Session, request: AskRequest) -> AskResponse:
    ai = AIProvider()
    query_embedding = ai.embed_query(request.pergunta)
    if settings.database_url.startswith("sqlite"):
        rows = _sqlite_rows(database, request, query_embedding)
    else:
        rows = _postgres_rows(database, request, query_embedding)

    if not rows:
        raise ValueError("Nenhum trecho indexado foi encontrado para os editais selecionados")

    selected: list[tuple[Chunk, Document, Edital, float]] = []
    per_document: dict[str, int] = defaultdict(int)
    for chunk, document, edital, raw_distance in rows:
        if per_document[document.id] >= 3:
            continue
        selected.append((chunk, document, edital, raw_distance))
        per_document[document.id] += 1
        if len(selected) >= request.top_k:
            break

    context_blocks: list[str] = []
    sources: list[SourceOut] = []
    for source_number, (chunk, document, edital, raw_distance) in enumerate(selected, start=1):
        page_label = f"p. {chunk.page_number}" if chunk.page_number is not None else "metadados"
        context_blocks.append(
            f"[Fonte {source_number} | Edital: {edital.title} | Documento: {document.title} | {page_label}]\n"
            f"{chunk.content}"
        )
        excerpt = " ".join(chunk.content.split())
        if len(excerpt) > 360:
            excerpt = excerpt[:357] + "..."
        similarity = max(0.0, min(1.0, 1.0 - raw_distance))
        url = document.source_url or edital.source_url
        if not url and document.local_path:
            url = f"/api/documents/{document.id}/file"
        sources.append(
            SourceOut(
                source_number=source_number,
                edital_id=edital.id,
                edital_title=edital.title,
                document_id=document.id,
                document_title=document.title,
                page_number=chunk.page_number,
                excerpt=excerpt,
                url=url,
                similarity=round(similarity, 4),
            )
        )

    answer = ai.answer_from_context(request.pergunta, context_blocks)
    return AskResponse(answer=answer, sources=sources)
