"""RAG retriever: markdown -> chunks -> embeddings -> FAISS -> top-k."""

from __future__ import annotations

import asyncio

from app.config import Settings
from app.logging_config import get_logger
from app.models.rag import RetrievedChunk
from app.rag.embeddings import OllamaEmbeddings
from app.rag.loader import load_chunks
from app.rag.store import RagStore

logger = get_logger(__name__)


class RagRetriever:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.embeddings = OllamaEmbeddings(
            model=settings.ollama_embed_model,
            base_url=settings.ollama_base_url,
            timeout=settings.ollama_request_timeout,
        )
        self.store = RagStore(settings.rag_index_dir, settings.ollama_embed_model)
        self._lock = asyncio.Lock()
        self._ready = False

    async def ensure_index(self, *, force: bool = False) -> None:
        if self._ready and not force:
            return
        async with self._lock:
            if self._ready and not force:
                return
            if force or not self.store.exists():
                logger.info("Building RAG index from %s", self.settings.knowledge_dir)
                chunks = load_chunks(
                    self.settings.knowledge_dir,
                    chunk_size=self.settings.rag_chunk_size,
                    chunk_overlap=self.settings.rag_chunk_overlap,
                )
                vectors = await self.embeddings.embed([c.text for c in chunks])
                self.store.build(chunks, vectors)
            self._ready = True

    async def retrieve(
        self, query: str, *, top_k: int | None = None
    ) -> list[RetrievedChunk]:
        top_k = top_k or self.settings.rag_top_k
        await self.ensure_index()
        query_vector = await self.embeddings.embed_one(query)
        matches = self.store.search(query_vector, top_k)
        return [
            RetrievedChunk(
                chunk_id=chunk.id,
                source=chunk.source,
                heading=chunk.heading,
                text=chunk.text,
                score=score,
            )
            for chunk, score in matches
        ]
