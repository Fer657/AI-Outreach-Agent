"""Typed application errors and their HTTP mapping.

Keeping errors in one place lets the API layer translate them into useful,
non-leaking responses for the UI.
"""

from __future__ import annotations


class AppError(Exception):
    """Base class for all expected application errors."""

    status_code: int = 500
    code: str = "internal_error"

    def __init__(self, message: str, *, detail: str | None = None) -> None:
        super().__init__(message)
        self.message = message
        self.detail = detail


class ConfigError(AppError):
    """Missing configuration (e.g. an API key) or invalid settings."""

    status_code = 500
    code = "configuration_error"


class ResearchError(AppError):
    """Research stage failed (search API, mock data missing, etc.)."""

    status_code = 502
    code = "research_error"


class SearchAPIError(ResearchError):
    status_code = 502
    code = "search_api_error"


class NoResultsError(ResearchError):
    """Research completed but returned no usable evidence."""

    status_code = 404
    code = "no_results"


class LLMError(AppError):
    """LLM provider failure or unusable structured output."""

    status_code = 502
    code = "llm_error"


class RAGError(AppError):
    """Knowledge base / vector store failure."""

    status_code = 500
    code = "rag_error"


class StorageError(AppError):
    status_code = 500
    code = "storage_error"


class NotFoundError(AppError):
    """A requested record (message, analysis, prospect) does not exist."""

    status_code = 404
    code = "not_found"
