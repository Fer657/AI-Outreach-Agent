"""API request/response schemas."""

from __future__ import annotations

from pydantic import BaseModel, Field

from app.models.outreach import OutreachChannel, OutreachDraft
from app.models.problem import Problem
from app.models.rag import RetrievedChunk
from app.models.research import ResearchBundle
from app.models.solution import SolutionMatch


class HealthResponse(BaseModel):
    status: str
    app: str
    version: str
    environment: str
    research_mode: str
    analysis_mode: str
    llm_provider: str
    llm_model: str
    rag_index_ready: bool
    knowledge_dir: str
    database: str


class ResearchResponse(BaseModel):
    prospect_id: int
    run_id: int
    bundle: ResearchBundle


class AnalyzeResponse(BaseModel):
    prospect_id: int
    analysis_id: int
    run_id: int
    mode: str
    engine: str
    bundle: ResearchBundle
    knowledge: list[RetrievedChunk]
    problems: list[Problem]
    solutions: list[SolutionMatch]
    outreach: list[OutreachDraft]


class OutreachMessage(BaseModel):
    id: int
    prospect_id: int
    analysis_id: int | None = None
    research_run_id: int | None = None
    channel: str
    status: str
    subject: str | None = None
    content: str
    confidence: float | None = None
    referenced_sources: list[str] = Field(default_factory=list)
    problem_title: str | None = None
    service: str | None = None
    created_at: str
    updated_at: str


class GenerateOutreachRequest(BaseModel):
    analysis_id: int
    problem_title: str
    service: str | None = None
    instructions: str | None = None


class RegenerateRequest(BaseModel):
    channel: OutreachChannel | None = None
    instructions: str | None = None


class MessageUpdateRequest(BaseModel):
    content: str | None = None
    subject: str | None = None
    status: str | None = None
