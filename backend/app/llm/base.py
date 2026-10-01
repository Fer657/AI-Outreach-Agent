"""Provider-agnostic LLM abstraction.

The rest of the application only ever talks to `LLMProvider`. Concrete
providers (OpenRouter, DeepSeek, Ollama) live in sibling modules and are
selected via configuration, so no DeepSeek-specific code leaks into the
application logic.
"""

from __future__ import annotations

import json
import re
from abc import ABC, abstractmethod
from typing import Any, Literal

import httpx

from app.errors import LLMError
from app.logging_config import get_logger

logger = get_logger(__name__)

Role = Literal["system", "user", "assistant"]


class ChatMessage(dict):
    """Lightweight chat message ({'role': ..., 'content': ...})."""

    def __init__(self, role: Role, content: str) -> None:
        super().__init__(role=role, content=content)


class LLMProvider(ABC):
    """Base class for all LLM providers."""

    name: str = "base"

    def __init__(
        self,
        *,
        model: str,
        temperature: float = 0.2,
        max_tokens: int = 2000,
        timeout: int = 90,
    ) -> None:
        self.model = model
        self.temperature = temperature
        self.max_tokens = max_tokens
        self.timeout = timeout

    # -- to be implemented by concrete providers ----------------------------
    @abstractmethod
    async def _chat(
        self,
        messages: list[ChatMessage],
        *,
        json_mode: bool = False,
    ) -> str:
        """Send messages and return raw assistant text."""

    # -- shared behaviour ---------------------------------------------------
    async def complete(self, system: str, user: str) -> str:
        messages = [ChatMessage("system", system), ChatMessage("user", user)]
        try:
            return await self._chat(messages)
        except LLMError:
            raise
        except httpx.TimeoutException as exc:
            raise LLMError(
                f"{self.name} request timed out after {self.timeout}s.",
                detail=str(exc),
            ) from exc
        except httpx.HTTPError as exc:
            raise LLMError(f"{self.name} request failed.", detail=str(exc)) from exc

    async def complete_json(
        self,
        system: str,
        user: str,
        *,
        max_retries: int = 1,
    ) -> Any:
        """Return parsed JSON, retrying once with a stricter instruction."""
        messages = [ChatMessage("system", system), ChatMessage("user", user)]
        last_error: str | None = None

        for attempt in range(max_retries + 1):
            try:
                raw = await self._chat(messages, json_mode=True)
            except httpx.TimeoutException as exc:
                raise LLMError(
                    f"{self.name} request timed out after {self.timeout}s.",
                    detail=str(exc),
                ) from exc
            except httpx.HTTPError as exc:
                raise LLMError(f"{self.name} request failed.", detail=str(exc)) from exc

            parsed = _extract_json(raw)
            if parsed is not None:
                return parsed

            last_error = raw[:500] if raw else "<empty response>"
            logger.warning(
                "LLM returned non-JSON output (attempt %s/%s) from %s",
                attempt + 1,
                max_retries + 1,
                self.name,
            )
            messages.append(ChatMessage("assistant", raw))
            messages.append(
                ChatMessage(
                    "user",
                    "Your previous reply was not valid JSON. Reply with ONLY a single "
                    "valid JSON object (no markdown, no commentary).",
                )
            )

        raise LLMError(
            "LLM did not return valid JSON after retry.",
            detail=str(last_error),
        )


_FENCE_RE = re.compile(r"```(?:json)?\s*(.*?)```", re.DOTALL | re.IGNORECASE)


def _extract_json(text: str) -> Any | None:
    """Best-effort extraction of a JSON value from an LLM response."""
    if not text:
        return None

    candidates: list[str] = []
    fenced = _FENCE_RE.search(text)
    if fenced:
        candidates.append(fenced.group(1).strip())
    candidates.append(text.strip())

    for candidate in candidates:
        try:
            return json.loads(candidate)
        except json.JSONDecodeError:
            pass
        # fall back to the outermost {...} or [...] block
        for opener, closer in (("{", "}"), ("[", "]")):
            start = candidate.find(opener)
            end = candidate.rfind(closer)
            if start != -1 and end != -1 and end > start:
                try:
                    return json.loads(candidate[start : end + 1])
                except json.JSONDecodeError:
                    continue
    return None
