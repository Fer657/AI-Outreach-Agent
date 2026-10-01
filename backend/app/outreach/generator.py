"""Outreach draft generation (and regeneration).

Drafts are tentative, source-grounded and always leave a human in the loop:
nothing here contacts a prospect. Two engines:

* heuristic (deterministic, no LLM)
* LLM (structured JSON), with automatic fallback to the heuristic engine
"""

from __future__ import annotations

from app.errors import LLMError
from app.llm.base import LLMProvider
from app.logging_config import get_logger
from app.models.outreach import OutreachChannel, OutreachDraft, OutreachStatus
from app.models.problem import Problem, Severity
from app.models.prospect import ProspectInput
from app.models.research import ResearchBundle
from app.models.signal import Signal
from app.models.solution import SolutionMatch

logger = get_logger(__name__)

_SEVERITY_WEIGHT = {Severity.LOW: 0, Severity.MEDIUM: 1, Severity.HIGH: 2}


def _first_name(prospect: ProspectInput) -> str:
    name = (prospect.prospect_name or "").strip()
    return name.split()[0] if name else "there"


def _best_problem(problems: list[Problem]) -> Problem | None:
    if not problems:
        return None
    return max(
        problems,
        key=lambda p: (_SEVERITY_WEIGHT[p.severity], p.confidence),
    )


def _best_signal(bundle: ResearchBundle) -> Signal | None:
    if not bundle.signals:
        return None
    return max(
        bundle.signals,
        key=lambda s: (s.relevance_score, s.recency_score, s.source_quality_score),
    )


def _solution_for(
    problem: Problem | None, solutions: list[SolutionMatch]
) -> SolutionMatch | None:
    if not solutions:
        return None
    if problem is not None:
        for solution in solutions:
            if solution.problem_title == problem.title:
                return solution
    return max(solutions, key=lambda s: s.relevance_score)


def _referenced_sources(
    problem: Problem | None,
    solution: SolutionMatch | None,
    signal: Signal | None,
) -> list[str]:
    refs: list[str] = []
    if signal and signal.source_url:
        refs.append(signal.source_url)
    if problem:
        refs.extend(problem.source_urls)
    if solution:
        refs.extend(solution.knowledge_sources)
    # de-duplicate, preserving order
    seen: set[str] = set()
    unique: list[str] = []
    for ref in refs:
        if ref and ref not in seen:
            seen.add(ref)
            unique.append(ref)
    return unique


def _confidence(problem: Problem | None, solution: SolutionMatch | None) -> float:
    values = [v for v in (problem.confidence if problem else None,
                          solution.relevance_score if solution else None)
              if v is not None]
    if not values:
        return 5.0
    return round(sum(values) / len(values), 1)


def _aligned_signal(problem: Problem | None, bundle: ResearchBundle) -> Signal | None:
    """Prefer the signal a problem was derived from, so body and subject agree."""
    if problem is not None and problem.related_signals:
        related = set(problem.related_signals)
        for signal in bundle.signals:
            if signal.title in related:
                return signal
    return _best_signal(bundle)


def _sentence(text: str | None, fallback: str) -> str:
    text = (text or "").strip()
    if not text:
        return fallback
    return text if text.endswith((".", "!", "?")) else f"{text}."


def heuristic_draft(
    prospect: ProspectInput,
    bundle: ResearchBundle,
    problem: Problem | None,
    solution: SolutionMatch | None,
    *,
    channel: OutreachChannel,
    instructions: str | None = None,
) -> OutreachDraft:
    company = prospect.company
    first = _first_name(prospect)
    signal = _aligned_signal(problem, bundle)

    problem_sentence = _sentence(
        problem.title if problem else None,
        "It looks like manual account research may be getting harder to keep "
        "consistent as the team grows.",
    )
    service = solution.service if solution else "Sales Intelligence"
    helps = (
        solution.how_it_helps
        if solution
        else "Northstar helps teams automate account research while keeping humans in "
        "the loop."
    )
    signal_sentence = ""
    if signal:
        title = signal.title.strip().rstrip(".")
        source = f" ({signal.source_name})" if signal.source_name else ""
        signal_sentence = f"{title}{source}."
    references = _referenced_sources(problem, solution, signal)

    if channel == OutreachChannel.LINKEDIN:
        opening = f"Hi {first},"
        if signal_sentence:
            opening += f" {signal_sentence}"
        body = (
            f"{opening} {problem_sentence} Northstar Labs helps teams with "
            f"{service.lower()}, always with a human in the loop. Open to a quick "
            f"conversation about how {company} handles this today?"
        )
        if instructions:
            body += f"\n\n(Context I wanted to include: {instructions.strip()})"
        return OutreachDraft(
            channel=channel,
            subject=None,
            body=body,
            status=OutreachStatus.DRAFT,
            confidence=_confidence(problem, solution),
            referenced_sources=references,
        )

    signal_block = f"{signal_sentence}\n\n" if signal_sentence else ""
    subject = signal.title if signal else f"A quick thought for {company}"
    body = (
        f"Hi {first},\n\n"
        f"{signal_block}"
        f"{problem_sentence}\n\n"
        f"At Northstar Labs we work on {service.lower()}. {helps}\n\n"
        f"Would it be useful to compare notes on how {company} handles this today? "
        f"Happy to share a short outline, no obligation.\n\n"
        f"Best,\nNorthstar Labs"
    )
    if instructions:
        body += f"\n\nP.S. {instructions.strip()}"

    return OutreachDraft(
        channel=channel,
        subject=subject,
        body=body,
        status=OutreachStatus.DRAFT,
        confidence=_confidence(problem, solution),
        referenced_sources=references,
    )


SYSTEM_PROMPT = """You are a thoughtful B2B outreach writer for Northstar Labs
(a fictional AI consultancy used for a demo).

Write ONE short, honest outreach message to a prospect. Rules:
1. Be tentative and respectful. Never state inferences as facts; use words like
   "may", "could" or "often".
2. Reference at most ONE concrete item from the supplied signals, and keep its
   real source URL in `referenced_sources`. Never invent facts or sources.
3. Do not claim any existing relationship with the prospect.
4. Keep it under ~160 words. No fake urgency, no hype.
5. `referenced_sources` MUST only contain URLs/sources supplied to you.
6. If `channel` is LINKEDIN, `subject` must be null and the message must be short.

Respond with ONLY a JSON object of this exact shape:
{
  "subject": "only for EMAIL, else null",
  "body": "the message",
  "referenced_sources": ["https://..."],
  "confidence": 0-10
}"""


def _build_user_prompt(
    prospect: ProspectInput,
    bundle: ResearchBundle,
    problems: list[Problem],
    solutions: list[SolutionMatch],
    channel: OutreachChannel,
    instructions: str | None,
) -> str:
    lines = [
        f"Channel: {channel.value}",
        f"Prospect name: {prospect.prospect_name}",
        f"Prospect title: {prospect.job_title or 'unknown'}",
        f"Company: {prospect.company}",
        f"Referral context: {prospect.referral or 'none'}",
        "",
    ]
    if problems:
        lines.append("INFERRED PROBLEMS (hypotheses):")
        for problem in problems[:3]:
            lines.append(f"- {problem.title}: {problem.description}")
        lines.append("")
    if solutions:
        lines.append("NORTHSTAR SERVICES THAT COULD HELP:")
        for solution in solutions[:3]:
            lines.append(f"- {solution.service}: {solution.how_it_helps}")
        lines.append("")
    if bundle.signals:
        lines.append("OBSERVED SIGNALS (real, cite source_url):")
        for signal in bundle.signals[:5]:
            lines.append(
                f"- [{signal.signal_type.value}] {signal.title} "
                f"(source_url: {signal.source_url}, source: {signal.source_name})"
            )
        lines.append("")
    if instructions:
        lines.append(f"Extra instructions from the sender: {instructions.strip()}")
    lines.append("Write the outreach message as JSON.")
    return "\n".join(lines)


async def llm_draft(
    prospect: ProspectInput,
    bundle: ResearchBundle,
    problems: list[Problem],
    solutions: list[SolutionMatch],
    llm: LLMProvider,
    *,
    channel: OutreachChannel,
    instructions: str | None = None,
) -> OutreachDraft:
    raw = await llm.complete_json(
        SYSTEM_PROMPT,
        _build_user_prompt(prospect, bundle, problems, solutions, channel, instructions),
    )
    if not isinstance(raw, dict):
        raise LLMError("Outreach generation returned an unexpected JSON shape.")

    body = str(raw.get("body", "")).strip()
    if not body:
        raise LLMError("Outreach generation returned an empty body.")

    allowed = {s.source_url for s in bundle.signals if s.source_url}
    for problem in problems:
        allowed.update(problem.source_urls)
    for solution in solutions:
        allowed.update(solution.knowledge_sources)

    refs = [
        str(ref).strip()
        for ref in raw.get("referenced_sources", [])
        if str(ref).strip() in allowed
    ]

    subject = raw.get("subject")
    if channel == OutreachChannel.LINKEDIN:
        subject = None
    elif subject is not None:
        subject = str(subject).strip() or None

    try:
        confidence = float(raw.get("confidence", 5.0))
    except (TypeError, ValueError):
        confidence = 5.0

    return OutreachDraft(
        channel=channel,
        subject=subject,
        body=body,
        status=OutreachStatus.DRAFT,
        confidence=max(0.0, min(10.0, confidence)),
        referenced_sources=refs or _referenced_sources(
            _best_problem(problems), _solution_for(_best_problem(problems), solutions),
            _best_signal(bundle),
        ),
    )


async def generate_draft(
    prospect: ProspectInput,
    bundle: ResearchBundle,
    problems: list[Problem],
    solutions: list[SolutionMatch],
    llm: LLMProvider | None,
    *,
    channel: OutreachChannel,
    instructions: str | None = None,
    prefer_llm: bool,
    problem: Problem | None = None,
    solution: SolutionMatch | None = None,
) -> tuple[OutreachDraft, bool]:
    """Return (draft, used_llm) for a single channel.

    When `problem`/`solution` are supplied (user-selected), the draft is scoped
    to that pair; otherwise the best-matching pair is chosen automatically.
    """
    resolved_problem = problem if problem is not None else _best_problem(problems)
    resolved_solution = (
        solution
        if solution is not None
        else _solution_for(resolved_problem, solutions)
    )
    scoped_problems = [resolved_problem] if resolved_problem is not None else []
    scoped_solutions = [resolved_solution] if resolved_solution is not None else []

    if prefer_llm and llm is not None:
        try:
            draft = await llm_draft(
                prospect,
                bundle,
                scoped_problems,
                scoped_solutions,
                llm,
                channel=channel,
                instructions=instructions,
            )
            return draft, True
        except LLMError as exc:
            logger.warning("LLM outreach generation failed: %s", exc.message)
        except Exception as exc:  # noqa: BLE001
            logger.warning("Unexpected outreach-generation error: %s", exc)

    return (
        heuristic_draft(
            prospect,
            bundle,
            resolved_problem,
            resolved_solution,
            channel=channel,
            instructions=instructions,
        ),
        False,
    )


async def generate_outreach(
    prospect: ProspectInput,
    bundle: ResearchBundle,
    problems: list[Problem],
    solutions: list[SolutionMatch],
    llm: LLMProvider | None,
    *,
    channels: tuple[OutreachChannel, ...] = (OutreachChannel.EMAIL,),
    instructions: str | None = None,
    prefer_llm: bool,
    problem: Problem | None = None,
    solution: SolutionMatch | None = None,
) -> tuple[list[OutreachDraft], bool]:
    """Return (drafts, used_llm). `used_llm` is True only if every channel used it."""
    drafts: list[OutreachDraft] = []
    all_llm = True
    for channel in channels:
        draft, used_llm = await generate_draft(
            prospect,
            bundle,
            problems,
            solutions,
            llm,
            channel=channel,
            instructions=instructions,
            prefer_llm=prefer_llm,
            problem=problem,
            solution=solution,
        )
        drafts.append(draft)
        all_llm = all_llm and used_llm
    return drafts, all_llm
