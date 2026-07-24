from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass(frozen=True)
class TextChunk:
    page_number: int | None
    chunk_index: int
    content: str


def normalize_text(text: str) -> str:
    text = text.replace("\x00", " ")
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def _choose_cut(text: str, start: int, target_end: int) -> int:
    if target_end >= len(text):
        return len(text)

    minimum = start + int((target_end - start) * 0.65)
    candidates = [
        text.rfind("\n\n", minimum, target_end),
        text.rfind(". ", minimum, target_end),
        text.rfind("; ", minimum, target_end),
        text.rfind("\n", minimum, target_end),
        text.rfind(" ", minimum, target_end),
    ]
    valid = [position for position in candidates if position >= minimum]
    if not valid:
        return target_end
    return max(valid) + 1


def chunk_pages(
    pages: list[tuple[int | None, str]],
    chunk_size: int = 1400,
    overlap: int = 220,
) -> list[TextChunk]:
    if chunk_size < 200:
        raise ValueError("chunk_size deve ser maior ou igual a 200")
    if overlap < 0 or overlap >= chunk_size:
        raise ValueError("overlap deve ser positivo e menor que chunk_size")

    chunks: list[TextChunk] = []
    global_index = 0

    for page_number, raw_text in pages:
        text = normalize_text(raw_text)
        if not text:
            continue

        start = 0
        while start < len(text):
            target_end = min(start + chunk_size, len(text))
            end = _choose_cut(text, start, target_end)
            content = text[start:end].strip()
            if content:
                chunks.append(
                    TextChunk(
                        page_number=page_number,
                        chunk_index=global_index,
                        content=content,
                    )
                )
                global_index += 1

            if end >= len(text):
                break
            next_start = max(end - overlap, start + 1)
            start = next_start

    return chunks
