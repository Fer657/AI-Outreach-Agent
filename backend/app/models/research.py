"""Research models: raw search results, scored evidence and the bundle."""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field

from app.models.signal import Signal


class SourceType(str, Enum):
    """Ordered roughly by the source priority defined in the spec."""

    COMPANY_WEBSITE = "COMPANY_WEBSITE"
    COMPANY_NEWSROOM = "COMPANY_NEWSROOM"
    COMPANY_CAREERS = "COMPANY_CAREERS"
    EXECUTIVE_POST = "EXECUTIVE_POST"
    NEWS_PUBLICATION = "NEWS_PUBLICATION"
    OTHER = "OTHER"


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


class SearchResult(BaseModel):
    """A single raw result returned by a research source."""

    title: str
    url: str
    content: str = ""
    source_name: str = ""
    source_type: SourceType = SourceType.OTHER
    published_date: str | None = None
    retrieved_date: str = Field(default_factory=utc_now_iso)
    query: str | None = None


class Evidence(SearchResult):
    """A search result that survived dedupe/filtering and was scored."""

    dedupe_key: str = ""
    relevance_score: float = Field(default=0.0, ge=0.0, le=10.0)
    source_quality_score: float = Field(default=0.0, ge=0.0, le=10.0)
    recency_score: float = Field(default=0.0, ge=0.0, le=10.0)
    rank_score: float = Field(default=0.0, ge=0.0, le=10.0)
    rationale: str = ""


class ResearchStats(BaseModel):
    queries_run: int = 0
    raw_results: int = 0
    after_dedupe: int = 0
    after_filtering: int = 0
    selected_evidence: int = 0


class ResearchBundle(BaseModel):
    """Output of the research + signal extraction stages."""

    company: str
    company_url: str | None = None
    mode: str = "mock"
    queries: list[str] = Field(default_factory=list)
    evidence: list[Evidence] = Field(default_factory=list)
    signals: list[Signal] = Field(default_factory=list)
    stats: ResearchStats = Field(default_factory=ResearchStats)
    generated_at: str = Field(default_factory=utc_now_iso)

    def to_public_dict(self) -> dict[str, Any]:
        return self.model_dump(mode="json")
