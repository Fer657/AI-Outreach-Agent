"""Shared implementation for OpenAI-compatible chat completion APIs.

Both OpenRouter and the direct DeepSeek API expose an OpenAI-compatible
`/chat/completions` endpoint, so they share this base class.
"""

from __future__ import annotations

import httpx

from app.errors import ConfigError, LLMError
from app.llm.base import ChatMessage, LLMProvider
from app.logging_config import get_logger

logger = get_logger(__name__)


class OpenAICompatibleProvider(LLMProvider):
    name = "openai_compatible"

    def __init__(
        self,
        *,
        model: str,
        api_key: str | None,
        base_url: str,
        temperature: float = 0.2,
        max_tokens: int = 2000,
        timeout: int = 90,
        extra_headers: dict[str, str] | None = None,
    ) -> None:
        super().__init__(
            model=model, temperature=temperature, max_tokens=max_tokens, timeout=timeout
        )
        if not api_key:
            raise ConfigError(
                f"{self.name}: missing API key. Set it in backend/.env "
                f"(no keys are hardcoded)."
            )
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self.extra_headers = extra_headers or {}

    async def _chat(
        self,
        messages: list[ChatMessage],
        *,
        json_mode: bool = False,
    ) -> str:
        url = f"{self.base_url}/chat/completions"
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
            **self.extra_headers,
        }
        payload: dict = {
            "model": self.model,
            "messages": list(messages),
            "temperature": self.temperature,
            "max_tokens": self.max_tokens,
        }
        if json_mode:
            payload["response_format"] = {"type": "json_object"}

        async with httpx.AsyncClient(timeout=self.timeout) as client:
            response = await client.post(url, headers=headers, json=payload)

            # Some models reject response_format; retry without it once.
            if response.status_code == 400 and json_mode:
                logger.warning("%s rejected json response_format; retrying plain", self.name)
                payload.pop("response_format", None)
                response = await client.post(url, headers=headers, json=payload)

        self._raise_for_status(response)

        try:
            data = response.json()
            return data["choices"][0]["message"]["content"] or ""
        except (ValueError, KeyError, IndexError, TypeError) as exc:
            raise LLMError(
                f"{self.name} returned an unexpected response shape.",
                detail=str(exc),
            ) from exc

    def _raise_for_status(self, response: httpx.Response) -> None:
        if response.status_code < 400:
            return
        snippet = response.text[:300]
        if response.status_code == 401:
            raise LLMError(f"{self.name} authentication failed (check API key).")
        if response.status_code == 429:
            raise LLMError(f"{self.name} rate limit reached. Try again shortly.")
        raise LLMError(
            f"{self.name} request failed with HTTP {response.status_code}.",
            detail=snippet,
        )
