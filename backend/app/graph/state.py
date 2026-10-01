"""Shared graph state for the analysis pipeline."""

from __future__ import annotations

from typing import TypedDict

from app.models.analysis import AnalysisBundle
from app.models.outreach import OutreachDraft
from app.models.problem import Problem
from app.models.prospect import ProspectInput
from app.models.rag import RetrievedChunk
from app.models.research import ResearchBundle
from app.models.solution import SolutionMatch


class AnalysisState(TypedDict, total=False):
    """Mutable state threaded through the LangGraph nodes.

    Every node returns a partial dict which LangGraph merges into this state.
    """

    prospect: ProspectInput
    prospect_id: int
    research_run_id: int
    mode: str
    engine: str

    research: ResearchBundle
    knowledge: list[RetrievedChunk]
    problems: list[Problem]
    solutions: list[SolutionMatch]
    outreach: list[OutreachDraft]
    analysis: AnalysisBundle
    analysis_id: int

    problems_llm: bool
    solutions_llm: bool
