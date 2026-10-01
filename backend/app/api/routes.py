"""HTTP routes.

Endpoints:
  GET   /api/health                          - liveness + configuration summary
  POST  /api/research                        - research + signal extraction
  POST  /api/analyze                         - full Phase 2 analysis pipeline
  GET   /api/prospects/{id}/messages         - outreach drafts for a prospect
  POST  /api/outreach/generate               - generate drafts for a chosen problem+solution
  PATCH /api/outreach/{id}                   - edit a draft (marks it EDITED)
  POST  /api/outreach/{id}/approve           - approve a draft
  POST  /api/outreach/{id}/regenerate        - regenerate a draft with the LLM/heuristic
"""

from __future__ import annotations

from fastapi import APIRouter, Request

from app.api.schemas import (
    AnalyzeResponse,
    GenerateOutreachRequest,
    HealthResponse,
    MessageUpdateRequest,
    OutreachMessage,
    RegenerateRequest,
    ResearchResponse,
)
from app.config import Settings
from app.errors import AppError, NotFoundError
from app.graph.workflow import run_analysis
from app.llm.base import LLMProvider
from app.llm.factory import get_llm_provider
from app.logging_config import get_logger
from app.models.analysis import AnalysisBundle
from app.models.outreach import OutreachChannel
from app.models.problem import Problem
from app.models.prospect import ProspectInput
from app.models.research import ResearchBundle
from app.models.solution import SolutionMatch
from app.outreach.generator import generate_draft, generate_outreach
from app.rag.retriever import RagRetriever
from app.research.service import ResearchService
from app.storage.db import Database, VALID_MESSAGE_STATUSES

logger = get_logger(__name__)

router = APIRouter(prefix="/api", tags=["analysis"])


def _settings(request: Request) -> Settings:
    return request.app.state.settings


def _database(request: Request) -> Database:
    return request.app.state.db


def _rag(request: Request) -> RagRetriever:
    return request.app.state.rag


def _llm_for(settings: Settings) -> LLMProvider | None:
    """Return a provider when needed; mock mode without LLM analysis needs none."""
    if settings.use_llm_analysis:
        return get_llm_provider(settings)
    if settings.is_mock:
        return None
    return get_llm_provider(settings)


def _message_response(record: dict) -> OutreachMessage:
    return OutreachMessage(
        id=record["id"],
        prospect_id=record["prospect_id"],
        analysis_id=record.get("analysis_id"),
        research_run_id=record.get("research_run_id"),
        channel=record["channel"],
        status=record["status"],
        subject=record.get("subject"),
        content=record["content"],
        confidence=record.get("confidence"),
        referenced_sources=record.get("referenced_sources") or [],
        problem_title=record.get("problem_title"),
        service=record.get("service"),
        created_at=record["created_at"],
        updated_at=record["updated_at"],
    )


@router.get("/health", response_model=HealthResponse)
async def health(request: Request) -> HealthResponse:
    settings = _settings(request)
    rag = _rag(request)
    llm_model = (
        settings.ollama_model if settings.llm_provider == "ollama" else settings.llm_model
    )
    return HealthResponse(
        status="ok",
        app=settings.app_name,
        version=settings.app_version,
        environment=settings.environment,
        research_mode=settings.research_mode,
        analysis_mode=settings.analysis_mode,
        llm_provider=settings.llm_provider,
        llm_model=llm_model,
        rag_index_ready=rag.store.exists(),
        knowledge_dir=str(settings.knowledge_dir),
        database=str(settings.sqlite_path),
    )


@router.post("/research", response_model=ResearchResponse)
async def research(request: Request, prospect: ProspectInput) -> ResearchResponse:
    settings = _settings(request)
    database = _database(request)

    bundle = await ResearchService(settings).run(prospect, _llm_for(settings))
    prospect_id = database.save_prospect(prospect)
    run_id = database.save_research_run(prospect_id, bundle)
    return ResearchResponse(prospect_id=prospect_id, run_id=run_id, bundle=bundle)


@router.post("/analyze", response_model=AnalyzeResponse)
async def analyze(request: Request, prospect: ProspectInput) -> AnalyzeResponse:
    """Run the full Phase 2 pipeline: research -> knowledge -> problems ->
    solutions -> outreach, persisting an analysis and its drafts."""
    settings = _settings(request)
    result = await run_analysis(
        settings=settings,
        llm=_llm_for(settings),
        rag=_rag(request),
        database=_database(request),
        prospect=prospect,
    )

    bundle: ResearchBundle = result["research"]
    return AnalyzeResponse(
        prospect_id=result["prospect_id"],
        analysis_id=result["analysis_id"],
        run_id=result["research_run_id"],
        mode=result["mode"],
        engine=result["engine"],
        bundle=bundle,
        knowledge=result["knowledge"],
        problems=result["problems"],
        solutions=result["solutions"],
        outreach=result["outreach"],
    )


@router.get("/prospects/{prospect_id}/messages", response_model=list[OutreachMessage])
async def list_prospect_messages(
    request: Request, prospect_id: int, limit: int = 50
) -> list[OutreachMessage]:
    database = _database(request)
    if database.get_prospect(prospect_id) is None:
        raise NotFoundError(f"Prospect #{prospect_id} was not found.")
    return [_message_response(row) for row in database.list_messages(prospect_id, limit=limit)]


def _load_message(database: Database, message_id: int) -> dict:
    record = database.get_message(message_id)
    if record is None:
        raise NotFoundError(f"Message #{message_id} was not found.")
    return record


def _load_analysis_bundle(database: Database, message: dict) -> AnalysisBundle:
    analysis_id = message.get("analysis_id")
    if analysis_id is None:
        raise AppError(
            "This draft is not linked to an analysis, so it cannot be regenerated.",
            detail="missing_analysis_link",
        )
    record = database.get_analysis(analysis_id)
    if record is None:
        raise NotFoundError(f"Analysis #{analysis_id} was not found.")
    return AnalysisBundle.model_validate(record["bundle"])


def _find_problem(bundle: AnalysisBundle, title: str | None) -> Problem | None:
    if not title:
        return None
    return next((p for p in bundle.problems if p.title == title), None)


def _find_solution(
    bundle: AnalysisBundle, problem: Problem | None, service: str | None
) -> SolutionMatch | None:
    candidates = [
        s
        for s in bundle.solutions
        if problem is not None and s.problem_title == problem.title
    ]
    if service:
        match = next((s for s in candidates if s.service == service), None)
        if match is not None:
            return match
    if candidates:
        return max(candidates, key=lambda s: s.relevance_score)
    if bundle.solutions:
        return max(bundle.solutions, key=lambda s: s.relevance_score)
    return None


@router.post("/outreach/generate", response_model=list[OutreachMessage])
async def generate_outreach_drafts(
    request: Request, payload: GenerateOutreachRequest
) -> list[OutreachMessage]:
    """Generate outreach drafts on demand for a user-selected problem + solution."""
    settings = _settings(request)
    database = _database(request)

    record = database.get_analysis(payload.analysis_id)
    if record is None:
        raise NotFoundError(f"Analysis #{payload.analysis_id} was not found.")
    bundle = AnalysisBundle.model_validate(record["bundle"])

    problem = _find_problem(bundle, payload.problem_title)
    if problem is None:
        raise NotFoundError(
            f"Problem {payload.problem_title!r} was not found in this analysis."
        )
    solution = _find_solution(bundle, problem, payload.service)

    drafts, _used_llm = await generate_outreach(
        bundle.prospect,
        bundle.research,
        bundle.problems,
        bundle.solutions,
        _llm_for(settings),
        channels=(OutreachChannel.EMAIL, OutreachChannel.LINKEDIN),
        instructions=payload.instructions,
        prefer_llm=settings.use_llm_analysis,
        problem=problem,
        solution=solution,
    )

    messages: list[OutreachMessage] = []
    for draft in drafts:
        message_id = database.save_message(
            record["prospect_id"],
            draft.body,
            research_run_id=record.get("research_run_id"),
            analysis_id=payload.analysis_id,
            channel=draft.channel.value,
            status=draft.status.value,
            subject=draft.subject,
            confidence=draft.confidence,
            referenced_sources=draft.referenced_sources,
            problem_title=problem.title,
            service=solution.service if solution else None,
        )
        saved = database.get_message(message_id)
        messages.append(_message_response(saved))

    logger.info(
        "Generated %s drafts for analysis #%s (problem=%r, solution=%r)",
        len(messages),
        payload.analysis_id,
        problem.title,
        solution.service if solution else None,
    )
    return messages


@router.patch("/outreach/{message_id}", response_model=OutreachMessage)
async def update_outreach(
    request: Request, message_id: int, payload: MessageUpdateRequest
) -> OutreachMessage:
    database = _database(request)
    message = _load_message(database, message_id)

    status = payload.status
    if status is not None and status not in VALID_MESSAGE_STATUSES:
        raise AppError(
            f"Invalid status {status!r}. Expected one of {', '.join(VALID_MESSAGE_STATUSES)}.",
            detail="invalid_status",
        )
    if status is None and (payload.content is not None or payload.subject is not None):
        status = "EDITED"

    updated = database.update_message(
        message_id,
        content=payload.content,
        subject=payload.subject,
        status=status,
    )
    logger.info("Updated message #%s (status=%s)", message_id, updated["status"])
    return _message_response(updated)


@router.post("/outreach/{message_id}/approve", response_model=OutreachMessage)
async def approve_outreach(request: Request, message_id: int) -> OutreachMessage:
    database = _database(request)
    _load_message(database, message_id)
    updated = database.set_message_status(message_id, "APPROVED")
    logger.info("Approved message #%s", message_id)
    return _message_response(updated)


@router.post("/outreach/{message_id}/regenerate", response_model=OutreachMessage)
async def regenerate_outreach(
    request: Request, message_id: int, payload: RegenerateRequest
) -> OutreachMessage:
    settings = _settings(request)
    database = _database(request)
    message = _load_message(database, message_id)
    bundle = _load_analysis_bundle(database, message)

    channel = payload.channel or OutreachChannel(message["channel"])
    problem = _find_problem(bundle, message.get("problem_title"))
    solution = (
        _find_solution(bundle, problem, message.get("service"))
        if problem is not None
        else None
    )
    draft, _used_llm = await generate_draft(
        bundle.prospect,
        bundle.research,
        bundle.problems,
        bundle.solutions,
        _llm_for(settings),
        channel=channel,
        instructions=payload.instructions,
        prefer_llm=settings.use_llm_analysis,
        problem=problem,
        solution=solution,
    )

    updated = database.update_message_generation(
        message_id,
        content=draft.body,
        subject=draft.subject,
        confidence=draft.confidence,
        referenced_sources=draft.referenced_sources,
    )
    logger.info("Regenerated message #%s (%s)", message_id, channel.value)
    return _message_response(updated)
