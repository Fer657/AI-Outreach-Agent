"""OpenRouter provider (DeepSeek models via OpenRouter by default)."""

from __future__ import annotations

from app.llm.openai_compat import OpenAICompatibleProvider

DEFAULT_MODEL = "deepseek/deepseek-chat"


class OpenRouterProvider(OpenAICompatibleProvider):
    name = "openrouter"

    def __init__(
        self,
        *,
        model: str | None,
        api_key: str | None,
        base_url: str = "https://openrouter.ai/api/v1",
        temperature: float = 0.2,
        max_tokens: int = 2000,
        timeout: int = 90,
    ) -> None:
        super().__init__(
            model=model or DEFAULT_MODEL,
            api_key=api_key,
            base_url=base_url,
            temperature=temperature,
            max_tokens=max_tokens,
            timeout=timeout,
            # Optional attribution headers recommended by OpenRouter.
            extra_headers={
                "HTTP-Referer": "https://localhost",
                "X-Title": "Northstar Labs Sales Intelligence",
            },
        )
