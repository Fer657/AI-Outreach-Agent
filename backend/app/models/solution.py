"""Solution-match models: map an inferred problem to a Northstar capability."""

from __future__ import annotations

from pydantic import BaseModel, Field


class SolutionMatch(BaseModel):
    problem_title: str
    service: str = Field(..., description="Northstar service, e.g. 'Sales Intelligence'")
    how_it_helps: str
    relevance_score: float = Field(default=5.0, ge=0.0, le=10.0)
    rationale: str = ""
    knowledge_sources: list[str] = Field(
        default_factory=list,
        description="Knowledge-base files/chunks this match is grounded in",
    )
