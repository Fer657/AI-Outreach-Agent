"""Application configuration.

All configuration is sourced from environment variables / `backend/.env`.
No API keys are ever hardcoded here.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# repo root: .../outreach agent  (backend/app/config.py -> parents[2])
ROOT_DIR = Path(__file__).resolve().parents[2]
BACKEND_DIR = ROOT_DIR / "backend"
DATA_DIR = BACKEND_DIR / "data"

LLMProviderName = Literal["openrouter", "deepseek", "ollama"]
ResearchMode = Literal["mock", "live"]
AnalysisMode = Literal["auto", "llm", "heuristic"]
SearchProviderName = Literal["tinyfish", "tavily"]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=(BACKEND_DIR / ".env", ROOT_DIR / ".env"),
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # ----- application ------------------------------------------------------
    app_name: str = "Northstar Labs Sales Intelligence API"
    app_version: str = "0.2.0-phase2"
    environment: str = "development"
    log_level: str = "INFO"

    # ----- CORS -------------------------------------------------------------
    # Comma-separated list of exact allowed origins. In development the regex
    # below additionally permits any localhost/127.0.0.1 port (Next may pick
    # 3001+ when 3000 is busy). Set CORS_ORIGIN_REGEX= (empty) to disable it.
    cors_origins: list[str] = [
        "http://localhost:3000",
        "http://127.0.0.1:3000",
    ]
    cors_origin_regex: str | None = r"^https?://(localhost|127\.0\.0\.1)(:\d+)?$"

    # ----- LLM --------------------------------------------------------------
    llm_provider: LLMProviderName = "ollama"
    llm_model: str = ""  # used by openrouter / deepseek
    llm_temperature: float = 0.2
    llm_max_tokens: int = 2000
    llm_request_timeout: int = 90

    openrouter_api_key: str | None = None
    openrouter_base_url: str = "https://openrouter.ai/api/v1"

    deepseek_api_key: str | None = None
    deepseek_base_url: str = "https://api.deepseek.com/v1"

    ollama_base_url: str = "http://localhost:11434"
    ollama_model: str = "qwen3:8b"
    ollama_embed_model: str = "nomic-embed-text"
    ollama_request_timeout: int = 180

    # ----- research ---------------------------------------------------------
    research_mode: ResearchMode = "mock"
    # How problem/solution/outreach generation is produced:
    #   auto      -> heuristic in mock mode, LLM in live mode
    #   llm       -> always try the LLM (falls back to heuristic on failure)
    #   heuristic -> always use deterministic rules (no LLM)
    analysis_mode: AnalysisMode = "auto"
    search_provider: SearchProviderName = "tinyfish"
    tavily_api_key: str | None = None
    tavily_base_url: str = "https://api.tavily.com"

    # TinyFish (search + fetch; free at any wallet balance)
    tinyfish_api_key: str | None = None
    tinyfish_search_url: str = "https://api.search.tinyfish.ai"
    tinyfish_fetch_url: str = "https://api.fetch.tinyfish.ai"
    tinyfish_location: str = "US"
    tinyfish_language: str = "en"

    top_k_per_query: int = 5
    max_queries: int = 5
    max_evidence: int = 12
    request_timeout: int = 30

    x_api_bearer_token: str | None = None
    x_api_base_url: str = "https://api.twitter.com/2"

    # ----- paths ------------------------------------------------------------
    knowledge_dir: Path = Field(default=ROOT_DIR / "knowledge")
    mock_dir: Path = Field(default=ROOT_DIR / "northstar" / "mock")
    sqlite_path: Path = Field(default=DATA_DIR / "northstar.db")
    rag_index_dir: Path = Field(default=DATA_DIR / "rag_index")

    # ----- RAG --------------------------------------------------------------
    rag_top_k: int = 4
    rag_chunk_size: int = 700
    rag_chunk_overlap: int = 100

    @field_validator("cors_origins", mode="before")
    @classmethod
    def _split_cors_origins(cls, value: object) -> object:
        """Accept either a JSON list or a comma-separated string."""
        if isinstance(value, str):
            return [item.strip() for item in value.split(",") if item.strip()]
        return value

    @field_validator("cors_origin_regex", mode="before")
    @classmethod
    def _blank_regex_to_none(cls, value: object) -> object:
        if isinstance(value, str) and not value.strip():
            return None
        return value

    @property
    def is_mock(self) -> bool:
        return self.research_mode == "mock"

    @property
    def use_llm_analysis(self) -> bool:
        """Whether the analysis stages should call the LLM."""
        if self.analysis_mode == "heuristic":
            return False
        if self.analysis_mode == "llm":
            return True
        return not self.is_mock


@lru_cache
def get_settings() -> Settings:
    return Settings()
