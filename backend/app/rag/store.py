"""FAISS-backed vector store for internal knowledge."""

from __future__ import annotations

import json
from pathlib import Path

import faiss
import numpy as np

from app.errors import RAGError
from app.logging_config import get_logger
from app.rag.loader import Chunk

logger = get_logger(__name__)


class RagStore:
    """Persisted FAISS index (inner product over L2-normalised vectors)."""

    def __init__(self, index_dir: Path, embed_model: str) -> None:
        self.index_dir = index_dir
        self.embed_model = embed_model
        self.index_file = index_dir / "index.faiss"
        self.meta_file = index_dir / "metadata.json"

    def exists(self) -> bool:
        return self.index_file.is_file() and self.meta_file.is_file()

    def build(self, chunks: list[Chunk], vectors: np.ndarray) -> None:
        if vectors.size == 0:
            raise RAGError("Cannot build RAG index: no vectors were produced.")
        if vectors.shape[0] != len(chunks):
            raise RAGError(
                "Cannot build RAG index: vector/chunk count mismatch "
                f"({vectors.shape[0]} != {len(chunks)})."
            )

        self.index_dir.mkdir(parents=True, exist_ok=True)
        index = faiss.IndexFlatIP(vectors.shape[1])
        index.add(vectors)
        faiss.write_index(index, str(self.index_file))

        metadata = {
            "embed_model": self.embed_model,
            "dimension": int(vectors.shape[1]),
            "chunks": [
                {
                    "chunk_id": chunk.id,
                    "source": chunk.source,
                    "heading": chunk.heading,
                    "text": chunk.text,
                }
                for chunk in chunks
            ],
        }
        self.meta_file.write_text(json.dumps(metadata, ensure_ascii=False), encoding="utf-8")
        logger.info(
            "Built RAG index: %s chunks, dim=%s, model=%s",
            len(chunks),
            vectors.shape[1],
            self.embed_model,
        )

    def _load(self) -> tuple[faiss.Index, list[dict], str | None]:
        try:
            index = faiss.read_index(str(self.index_file))
            metadata = json.loads(self.meta_file.read_text(encoding="utf-8"))
        except (OSError, ValueError, RuntimeError) as exc:
            raise RAGError("Could not load RAG index from disk.", detail=str(exc)) from exc
        return index, metadata.get("chunks", []), metadata.get("embed_model")

    def search(self, query_vector: np.ndarray, top_k: int) -> list[tuple[Chunk, float]]:
        if not self.exists():
            raise RAGError("RAG index has not been built yet.")
        index, chunk_rows, indexed_model = self._load()

        if indexed_model and indexed_model != self.embed_model:
            raise RAGError(
                "RAG index was built with a different embedding model "
                f"({indexed_model}); rebuild the index."
            )

        query = query_vector.reshape(1, -1).astype("float32")
        scores, indices = index.search(query, top_k)

        matches: list[tuple[Chunk, float]] = []
        for score, idx in zip(scores[0], indices[0]):
            if idx < 0 or idx >= len(chunk_rows):
                continue
            row = chunk_rows[idx]
            chunk = Chunk(
                id=row["chunk_id"],
                source=row["source"],
                heading=row.get("heading", ""),
                text=row["text"],
            )
            matches.append((chunk, float(score)))
        return matches
