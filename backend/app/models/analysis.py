"""Aggregate analysis model (Phase 2 output)."""

from __future__ import annotations

from pydantic import BaseModel, Field

from app.models.outreach import OutreachDraft
from app.models.problem import Problem
from app.models.prospect import ProspectInput
from app.models.rag import RetrievedChunk
from app.models.research import ResearchBundle, utc_now_iso
from app.models.solution import SolutionMatch


class AnalysisBundle(BaseModel):
    prospect: ProspectInput
    mode: str = "mock"
    engine: str = "heuristic"
    research: ResearchBundle
    knowledge: list[RetrievedChunk] = Field(default_factory=list)
    problems: list[Problem] = Field(default_factory=list)
    solutions: list[SolutionMatch] = Field(default_factory=list)
    outreach: list[OutreachDraft] = Field(default_factory=list)
    generated_at: str = Field(default_factory=utc_now_iso)
