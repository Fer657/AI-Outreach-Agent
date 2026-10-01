"""Solution matching: map each inferred problem to a Northstar capability.

Both engines ground their output in the *retrieved internal knowledge* so every
match can point at the knowledge chunks (and files) it is based on.
"""

from __future__ import annotations

from app.errors import LLMError
from app.llm.base import LLMProvider
from app.logging_config import get_logger
from app.models.problem import Problem
from app.models.prospect import ProspectInput
from app.models.rag import RetrievedChunk
from app.models.solution import SolutionMatch

logger = get_logger(__name__)

SERVICES = (
    "Sales Intelligence",
    "AI Automation",
    "RAG Systems",
    "Data Engineering",
    "AI Product Engineering",
)

# Service -> keywords that indicate a fit. Scores are summed across the problem.
_SERVICE_KEYWORDS: dict[str, tuple[str, ...]] = {
    "Sales Intelligence": (
        "research",
        "account",
        "prospect",
        "qualification",
        "sales",
        "lead",
        "outreach",
        "icp",
        "signal",
        "crm",
    ),
    "AI Automation": (
        "manual",
        "repetitive",
        "workflow",
        "process",
        "onboarding",
        "automation",
        "document",
        "classification",
        "administrative",
    ),
    "RAG Systems": (
        "documentation",
        "knowledge",
        "internal",
        "retrieval",
        "enablement",
        "information",
        "answer",
        "sop",
    ),
    "Data Engineering": (
        "data",
        "integration",
        "fragment",
        "pipeline",
        "systems",
        "reconciliation",
        "quality",
    ),
    "AI Product Engineering": (
        "dashboard",
        "assistant",
        "platform",
        "recommendation",
        "product",
        "saas",
    ),
}

_HOW_IT_HELPS: dict[str, str] = {
    "Sales Intelligence": (
        "Northstar's Sales Intelligence work automates account research and "
        "qualification, turning public signals into structured, consistent research "
        "briefs a team can review before outreach."
    ),
    "AI Automation": (
        "Northstar designs AI-assisted workflows that take repetitive, "
        "knowledge-intensive steps and automate them while keeping a human in the "
        "loop for important decisions."
    ),
    "RAG Systems": (
        "Northstar builds retrieval-augmented generation systems so teams can query "
        "internal documentation and knowledge bases and get grounded, current answers."
    ),
    "Data Engineering": (
        "Northstar builds data pipelines and integrations that bring information from "
        "multiple systems into one structured, reliable source of truth."
    ),
    "AI Product Engineering": (
        "Northstar builds custom AI-powered applications such as internal assistants, "
        "research platforms and intelligent dashboards."
    ),
}


def _problem_text(problem: Problem) -> str:
    return f"{problem.title} {problem.description} {problem.rationale}".lower()


def _score_service(service: str, text: str) -> int:
    return sum(text.count(keyword) for keyword in _SERVICE_KEYWORDS[service])


def _supporting_chunks(
    service: str, problem: Problem, knowledge: list[RetrievedChunk], *, limit: int = 2
) -> list[RetrievedChunk]:
    keywords = _SERVICE_KEYWORDS[service]
    problem_text = _problem_text(problem)

    def relevance(chunk: RetrievedChunk) -> int:
        text = f"{chunk.heading} {chunk.text}".lower()
        return sum(text.count(keyword) for keyword in keywords) + (
            2 if any(keyword in problem_text for keyword in keywords) else 0
        )

    ranked = sorted(knowledge, key=relevance, reverse=True)
    return [chunk for chunk in ranked if relevance(chunk) > 0][:limit] or ranked[:limit]


def heuristic_solutions(
    problems: list[Problem], knowledge: list[RetrievedChunk]
) -> list[SolutionMatch]:
    matches: list[SolutionMatch] = []
    for problem in problems:
        text = _problem_text(problem)
        best_service = max(SERVICES, key=lambda service: _score_service(service, text))
        if _score_service(best_service, text) == 0:
            best_service = "AI Automation"

        support = _supporting_chunks(best_service, problem, knowledge)
        sources = sorted({f"{chunk.source} · {chunk.heading}" for chunk in support})
        rationale = (
            f"Inferred problem '{problem.title}' maps most directly to Northstar's "
            f"{best_service} service."
        )
        if sources:
            rationale += " Grounded in: " + "; ".join(sources) + "."

        matches.append(
            SolutionMatch(
                problem_title=problem.title,
                service=best_service,
                how_it_helps=_HOW_IT_HELPS[best_service],
                relevance_score=round(min(10.0, problem.confidence), 1),
                rationale=rationale,
                knowledge_sources=sources,
            )
        )
    return matches


SYSTEM_PROMPT = f"""You are a solutions consultant at Northstar Labs (a fictional
B2B AI consultancy used for a demo).

For each inferred prospect PROBLEM, pick the single best-fitting Northstar service
and explain how it could help. You are given Northstar's internal knowledge as
snippets.

Allowed services: {", ".join(SERVICES)}.

Rules:
1. Only use the supplied problems and knowledge. Do not invent capabilities.
2. `service` MUST be one of the allowed services.
3. `knowledge_sources` MUST copy the `source` values of the knowledge snippets used.
4. `relevance_score` is a 0-10 number.
5. Keep `how_it_helps` to one or two sentences.

Respond with ONLY a JSON object:
{{
  "solutions": [
    {{
      "problem_title": "exact problem title",
      "service": "Sales Intelligence",
      "how_it_helps": "...",
      "relevance_score": 7.5,
      "rationale": "...",
      "knowledge_sources": ["file.md · Heading"]
    }}
  ]
}}"""


def _build_user_prompt(
    prospect: ProspectInput,
    problems: list[Problem],
    knowledge: list[RetrievedChunk],
) -> str:
    lines = [f"Prospect company: {prospect.company}", "", f"PROBLEMS ({len(problems)}):"]
    for index, problem in enumerate(problems, start=1):
        lines.append(f"[{index}] {problem.title}\n    {problem.description}")
    lines.append("")
    lines.append(f"NORTHSTAR KNOWLEDGE ({len(knowledge)} snippets):")
    for index, chunk in enumerate(knowledge, start=1):
        lines.append(
            f"[{index}] source={chunk.source} · {chunk.heading}\n    {chunk.text[:500]}"
        )
    lines.append("")
    lines.append("Match each problem to the best service as JSON.")
    return "\n".join(lines)


async def llm_solutions(
    prospect: ProspectInput,
    problems: list[Problem],
    knowledge: list[RetrievedChunk],
    llm: LLMProvider,
) -> list[SolutionMatch]:
    raw = await llm.complete_json(
        SYSTEM_PROMPT, _build_user_prompt(prospect, problems, knowledge)
    )

    if isinstance(raw, dict):
        raw_solutions = raw.get("solutions", [])
    elif isinstance(raw, list):
        raw_solutions = raw
    else:
        raise LLMError("Solution matching returned an unexpected JSON shape.")
    if not isinstance(raw_solutions, list):
        raise LLMError("Solution matching: 'solutions' was not a list.")

    by_title = {problem.title: problem for problem in problems}
    valid_sources = {f"{chunk.source} · {chunk.heading}" for chunk in knowledge}

    matches: list[SolutionMatch] = []
    for item in raw_solutions:
        if not isinstance(item, dict):
            continue
        title = str(item.get("problem_title", "")).strip()
        problem = by_title.get(title)
        if problem is None:
            logger.warning("Discarding solution for unknown problem: %r", title)
            continue
        service = str(item.get("service", "")).strip()
        if service not in SERVICES:
            logger.warning("Discarding solution with unknown service: %r", service)
            continue
        sources = [
            str(src).strip()
            for src in item.get("knowledge_sources", [])
            if str(src).strip() in valid_sources
        ]
        try:
            matches.append(
                SolutionMatch(
                    problem_title=problem.title,
                    service=service,
                    how_it_helps=str(item.get("how_it_helps", "")).strip(),
                    relevance_score=float(item.get("relevance_score", problem.confidence)),
                    rationale=str(item.get("rationale", "")).strip(),
                    knowledge_sources=sorted(set(sources)),
                )
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning("Discarding invalid solution: %s", exc)

    return matches


async def match_solutions(
    prospect: ProspectInput,
    problems: list[Problem],
    knowledge: list[RetrievedChunk],
    llm: LLMProvider | None,
    *,
    prefer_llm: bool,
) -> tuple[list[SolutionMatch], bool]:
    """Return (solutions, used_llm). Falls back to the heuristic engine."""
    if not problems:
        return [], False

    if prefer_llm and llm is not None:
        try:
            solutions = await llm_solutions(prospect, problems, knowledge, llm)
            if solutions:
                return solutions, True
            logger.warning("LLM returned no solutions; using heuristic fallback.")
        except LLMError as exc:
            logger.warning("LLM solution matching failed: %s", exc.message)
        except Exception as exc:  # noqa: BLE001
            logger.warning("Unexpected solution-matching error: %s", exc)

    return heuristic_solutions(problems, knowledge), False
