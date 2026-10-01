"""Factory that builds the configured LLM provider."""

from __future__ import annotations

from app.config import Settings
from app.errors import ConfigError
from app.llm.base import LLMProvider
from app.llm.deepseek import DeepSeekProvider
from app.llm.ollama import OllamaProvider
from app.llm.openrouter import OpenRouterProvider


def get_llm_provider(settings: Settings) -> LLMProvider:
    """Instantiate the provider named by `LLM_PROVIDER`."""
    provider = settings.llm_provider

    if provider == "openrouter":
        return OpenRouterProvider(
            model=settings.llm_model,
            api_key=settings.openrouter_api_key,
            base_url=settings.openrouter_base_url,
            temperature=settings.llm_temperature,
            max_tokens=settings.llm_max_tokens,
            timeout=settings.llm_request_timeout,
        )

    if provider == "deepseek":
        return DeepSeekProvider(
            model=settings.llm_model,
            api_key=settings.deepseek_api_key,
            base_url=settings.deepseek_base_url,
            temperature=settings.llm_temperature,
            max_tokens=settings.llm_max_tokens,
            timeout=settings.llm_request_timeout,
        )

    if provider == "ollama":
        return OllamaProvider(
            model=settings.ollama_model,
            base_url=settings.ollama_base_url,
            temperature=settings.llm_temperature,
            max_tokens=settings.llm_max_tokens,
            timeout=settings.ollama_request_timeout,
        )

    raise ConfigError(f"Unsupported LLM_PROVIDER: {provider!r}")
