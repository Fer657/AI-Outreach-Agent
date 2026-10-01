"""Knowledge base loading and chunking (markdown -> chunks)."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

from app.errors import RAGError
from app.logging_config import get_logger

logger = get_logger(__name__)


@dataclass
class Chunk:
    id: str
    source: str
    heading: str
    text: str
    metadata: dict = field(default_factory=dict)


def _split_sections(markdown: str) -> list[tuple[str, str]]:
    """Split markdown into (heading, body) sections based on '##' headings."""
    lines = markdown.splitlines()
    sections: list[tuple[str, str]] = []
    current_heading = "Overview"
    buffer: list[str] = []

    for line in lines:
        if re.match(r"^#{1,3}\s+", line):
            if buffer and "".join(buffer).strip():
                sections.append((current_heading, "\n".join(buffer).strip()))
            current_heading = re.sub(r"^#{1,3}\s+", "", line).strip()
            buffer = []
        else:
            buffer.append(line)

    if buffer and "".join(buffer).strip():
        sections.append((current_heading, "\n".join(buffer).strip()))

    return sections


def _chunk_text(text: str, size: int, overlap: int) -> list[str]:
    """Paragraph-aware chunking that falls back to hard splits for long blocks."""
    paragraphs = [p.strip() for p in re.split(r"\n\s*\n", text) if p.strip()]
    chunks: list[str] = []
    buffer = ""

    for paragraph in paragraphs:
        if len(paragraph) > size:
            if buffer:
                chunks.append(buffer.strip())
                buffer = ""
            step = max(size - overlap, 1)
            for start in range(0, len(paragraph), step):
                piece = paragraph[start : start + size]
                if piece.strip():
                    chunks.append(piece.strip())
                if start + size >= len(paragraph):
                    break
            continue

        candidate = f"{buffer}\n\n{paragraph}".strip() if buffer else paragraph
        if len(candidate) <= size:
            buffer = candidate
        else:
            if buffer:
                chunks.append(buffer.strip())
            buffer = paragraph

    if buffer.strip():
        chunks.append(buffer.strip())
    return chunks


def load_chunks(
    knowledge_dir: Path, *, chunk_size: int, chunk_overlap: int
) -> list[Chunk]:
    if not knowledge_dir.is_dir():
        raise RAGError(f"Knowledge directory not found: {knowledge_dir}")

    files = sorted(knowledge_dir.glob("*.md"))
    if not files:
        raise RAGError(f"No markdown documents found in {knowledge_dir}")

    chunks: list[Chunk] = []
    for path in files:
        try:
            markdown = path.read_text(encoding="utf-8")
        except OSError as exc:
            raise RAGError(f"Could not read knowledge file {path.name}.", detail=str(exc)) from exc

        for heading, body in _split_sections(markdown):
            for index, piece in enumerate(_chunk_text(body, chunk_size, chunk_overlap)):
                chunks.append(
                    Chunk(
                        id=f"{path.stem}::{heading}::{index}",
                        source=path.name,
                        heading=heading,
                        text=piece,
                        metadata={"file": path.name, "heading": heading},
                    )
                )

    logger.info("Loaded %s chunks from %s knowledge documents", len(chunks), len(files))
    return chunks
