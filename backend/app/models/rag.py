"""RAG retrieval models."""

from __future__ import annotations

from pydantic import BaseModel, Field


class RetrievedChunk(BaseModel):
    chunk_id: str
    source: str
    heading: str
    text: str
    score: float = Field(..., description="Cosine similarity in [-1, 1]")
