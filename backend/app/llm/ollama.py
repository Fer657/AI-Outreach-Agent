"""Ollama provider — local/offline LLM fallback (e.g. qwen3:8b)."""

from __future__ import annotations

import httpx

from app.errors import LLMError
from app.llm.base import ChatMessage, LLMProvider
from app.logging_config import get_logger

logger = get_logger(__name__)

DEFAULT_MODEL = "qwen3:8b"


class OllamaProvider(LLMProvider):
    name = "ollama"

    def __init__(
        self,
        *,
        model: str | None,
        base_url: str = "http://localhost:11434",
        temperature: float = 0.2,
        max_tokens: int = 2000,
        timeout: int = 180,
    ) -> None:
        super().__init__(
            model=model or DEFAULT_MODEL,
            temperature=temperature,
            max_tokens=max_tokens,
            timeout=timeout,
        )
        self.base_url = base_url.rstrip("/")

    async def _chat(
        self,
        messages: list[ChatMessage],
        *,
        json_mode: bool = False,
    ) -> str:
        url = f"{self.base_url}/api/chat"
        payload: dict = {
            "model": self.model,
            "messages": list(messages),
            "stream": False,
            "think": False,
            "options": {
                "temperature": self.temperature,
                "num_predict": self.max_tokens,
            },
        }
        if json_mode:
            payload["format"] = "json"

        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.post(url, json=payload)
                if response.status_code == 400 and "think" in payload:
                    # Older servers / models may reject `think`.
                    logger.debug("Ollama rejected `think`; retrying without it")
                    payload.pop("think", None)
                    response = await client.post(url, json=payload)
        except httpx.ConnectError as exc:
            raise LLMError(
                f"Could not reach Ollama at {self.base_url}. Is `ollama serve` running?",
                detail=str(exc),
            ) from exc
        except httpx.TimeoutException as exc:
            raise LLMError(
                f"Ollama timed out after {self.timeout}s (model: {self.model}).",
                detail=str(exc),
            ) from exc
        except httpx.HTTPError as exc:
            raise LLMError("Ollama request failed.", detail=str(exc)) from exc

        if response.status_code == 404:
            raise LLMError(
                f"Ollama model '{self.model}' not found. Run: ollama pull {self.model}"
            )
        if response.status_code >= 400:
            raise LLMError(
                f"Ollama request failed with HTTP {response.status_code}.",
                detail=response.text[:300],
            )

        try:
            return response.json()["message"]["content"] or ""
        except (ValueError, KeyError, TypeError) as exc:
            raise LLMError("Ollama returned an unexpected response shape.", detail=str(exc)) from exc
