"""Local embeddings via Ollama (keeps internal knowledge on-premises).

Model is configurable (`OLLAMA_EMBED_MODEL`, default nomic-embed-text).
No internal document text is sent to an external embedding provider.
"""

from __future__ import annotations

import httpx
import numpy as np

from app.errors import RAGError
from app.logging_config import get_logger

logger = get_logger(__name__)


class OllamaEmbeddings:
    def __init__(
        self,
        *,
        model: str = "nomic-embed-text",
        base_url: str = "http://localhost:11434",
        timeout: int = 180,
    ) -> None:
        self.model = model
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout

    async def embed(self, texts: list[str]) -> np.ndarray:
        """Embed texts and return a float32 matrix with L2-normalised rows."""
        if not texts:
            return np.zeros((0, 0), dtype="float32")

        vectors = await self._embed_modern(texts)
        matrix = np.asarray(vectors, dtype="float32")
        norms = np.linalg.norm(matrix, axis=1, keepdims=True)
        norms[norms == 0] = 1.0
        return matrix / norms

    async def embed_one(self, text: str) -> np.ndarray:
        matrix = await self.embed([text])
        return matrix[0]

    async def _embed_modern(self, texts: list[str]) -> list[list[float]]:
        """Newer Ollama endpoint: POST /api/embed {model, input: [...]}."""
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.post(
                    f"{self.base_url}/api/embed",
                    json={"model": self.model, "input": texts},
                )
        except httpx.ConnectError as exc:
            raise RAGError(
                f"Could not reach Ollama at {self.base_url} for embeddings. "
                "Is `ollama serve` running?",
                detail=str(exc),
            ) from exc
        except httpx.HTTPError as exc:
            raise RAGError("Ollama embedding request failed.", detail=str(exc)) from exc

        if response.status_code == 404:
            raise RAGError(
                f"Ollama embedding model '{self.model}' not found. "
                f"Run: ollama pull {self.model}"
            )
        if response.status_code < 400:
            data = response.json()
            if "embeddings" in data:
                return data["embeddings"]

        # Fall back to the legacy per-prompt endpoint.
        logger.debug("Falling back to legacy /api/embeddings endpoint")
        return await self._embed_legacy(texts)

    async def _embed_legacy(self, texts: list[str]) -> list[list[float]]:
        vectors: list[list[float]] = []
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            for text in texts:
                try:
                    response = await client.post(
                        f"{self.base_url}/api/embeddings",
                        json={"model": self.model, "prompt": text},
                    )
                except httpx.HTTPError as exc:
                    raise RAGError(
                        "Ollama legacy embedding request failed.", detail=str(exc)
                    ) from exc
                if response.status_code >= 400:
                    raise RAGError(
                        f"Ollama embeddings returned HTTP {response.status_code}.",
                        detail=response.text[:200],
                    )
                vectors.append(response.json()["embedding"])
        return vectors
