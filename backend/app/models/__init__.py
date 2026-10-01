"""Pydantic model package."""

from app.models.analysis import AnalysisBundle
from app.models.outreach import OutreachChannel, OutreachDraft, OutreachStatus
from app.models.problem import Problem, Severity
from app.models.prospect import ProspectInput
from app.models.rag import RetrievedChunk
from app.models.research import (
    Evidence,
    ResearchBundle,
    SearchResult,
    SourceType,
)
from app.models.signal import Signal, SignalType
from app.models.solution import SolutionMatch

__all__ = [
    "ProspectInput",
    "SearchResult",
    "Evidence",
    "ResearchBundle",
    "SourceType",
    "Signal",
    "SignalType",
    "RetrievedChunk",
    "Problem",
    "Severity",
    "SolutionMatch",
    "OutreachChannel",
    "OutreachDraft",
    "OutreachStatus",
    "AnalysisBundle",
]
