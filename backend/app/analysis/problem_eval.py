"""Problem evaluation: turn observable signals into *inferred* business problems.

Two engines live here:

* `heuristic_problems` — deterministic, rule-based, no LLM (used in mock mode).
* `llm_problems`       — structured extraction via the configured LLM.

Both obey the same contract: a problem is an inference, so it must be phrased
tentatively ("may", "could") and every problem keeps the real source URLs of the
signals it was derived from. No source is ever fabricated.
"""

from __future__ import annotations

from dataclasses import dataclass

from app.errors import LLMError
from app.llm.base import LLMProvider
from app.logging_config import get_logger
from app.models.problem import Problem, Severity
from app.models.prospect import ProspectInput
from app.models.research import ResearchBundle
from app.models.signal import Signal, SignalType

logger = get_logger(__name__)

MAX_PROBLEMS = 4


@dataclass(frozen=True)
class _Rule:
    title: str
    description: str
    rationale: str
    severity: Severity


# Signal type -> inferred problem template. Wording is deliberately tentative.
_RULES: dict[SignalType, _Rule] = {
    SignalType.HIRING: _Rule(
        title="Rapid hiring may increase manual research and onboarding load",
        description=(
            "The company appears to be hiring across multiple teams. As "
            "customer-facing and operations headcount grows, the volume of manual "
            "account research, qualification and repetitive administrative work may "
            "grow faster than existing processes, which could create onboarding and "
            "consistency bottlenecks."
        ),
        rationale=(
            "Rapid hiring is a common trigger for rising manual workload and "
            "inconsistent process execution."
        ),
        severity=Severity.MEDIUM,
    ),
    SignalType.EXPANSION: _Rule(
        title="Expansion may increase account volume and research burden",
        description=(
            "The company is expanding into new markets or segments. Expansion often "
            "increases the number of target accounts and the manual research required "
            "per account, which may strain a sales team that is not yet automated."
        ),
        rationale=(
            "Geographic or market expansion is frequently accompanied by a higher "
            "volume of prospect research."
        ),
        severity=Severity.HIGH,
    ),
    SignalType.PRODUCT_LAUNCH: _Rule(
        title="Faster product releases may strain enablement and documentation",
        description=(
            "The company is shipping new product capabilities. Faster release cycles "
            "can outpace internal documentation and sales enablement, so teams may "
            "struggle to find current, consistent product knowledge when talking to "
            "customers."
        ),
        rationale=(
            "Rapid product change often creates gaps between what is released and what "
            "internal teams can easily retrieve."
        ),
        severity=Severity.MEDIUM,
    ),
    SignalType.ACQUISITION: _Rule(
        title="Acquisitions may fragment data and internal knowledge",
        description=(
            "The company is acquiring another business. Acquisitions commonly leave "
            "data and knowledge spread across separate systems, which may increase "
            "manual reconciliation and make it harder for teams to work from a single "
            "source of truth."
        ),
        rationale=(
            "Acquisitions are a well-known driver of data fragmentation and knowledge "
            "silos."
        ),
        severity=Severity.HIGH,
    ),
    SignalType.PARTNERSHIP: _Rule(
        title="New partnerships may increase integration and coordination work",
        description=(
            "The company announced a new partnership. Partnerships usually require "
            "additional data sharing and integration work, which may add manual, "
            "repetitive coordination tasks across teams."
        ),
        rationale=(
            "New partnerships tend to expand the surface area of systems and processes "
            "that must stay aligned."
        ),
        severity=Severity.MEDIUM,
    ),
    SignalType.FUNDING: _Rule(
        title="New funding may accelerate hiring and operational complexity",
        description=(
            "The company has raised or is investing new capital. Funding frequently "
            "accelerates hiring and go-to-market spend, which may increase operational "
            "complexity and the manual workload that comes with scaling quickly."
        ),
        rationale=(
            "Funding events are a strong leading indicator of rapid organizational "
            "growth."
        ),
        severity=Severity.HIGH,
    ),
    SignalType.LEADERSHIP: _Rule(
        title="Leadership changes may shift priorities and create process churn",
        description=(
            "There has been a leadership change or announcement. New leadership often "
            "revisits tooling and processes, which may create short-term churn in how "
            "teams research accounts and qualify opportunities."
        ),
        rationale=(
            "Leadership transitions commonly precede changes in process and tooling."
        ),
        severity=Severity.LOW,
    ),
    SignalType.TECHNOLOGY: _Rule(
        title="Technology changes may require workflow and data integration work",
        description=(
            "The company appears to be adopting or changing technology. New systems "
            "often need to be integrated with existing workflows, which may add manual "
            "data handling until integrations are in place."
        ),
        rationale=(
            "Technology changes generally imply follow-on integration and process work."
        ),
        severity=Severity.MEDIUM,
    ),
    SignalType.CUSTOMER: _Rule(
        title="Customer growth may increase repetitive research and support work",
        description=(
            "The company is growing its customer base. More customers typically means "
            "more repetitive research, account management and support work, which may "
            "outpace a manual approach."
        ),
        rationale=(
            "Customer growth tends to scale repetitive, knowledge-intensive tasks."
        ),
        severity=Severity.MEDIUM,
    ),
    SignalType.OPERATIONAL: _Rule(
        title="Operational scaling may increase repetitive manual knowledge work",
        description=(
            "The company is scaling its operations. Scaling usually multiplies "
            "repetitive, knowledge-intensive tasks that may not be well supported by "
            "the current manual processes."
        ),
        rationale=(
            "Operational scale is a common driver of manual knowledge-work bottlenecks."
        ),
        severity=Severity.MEDIUM,
    ),
    SignalType.EXECUTIVE_STATEMENT: _Rule(
        title="Stated growth plans may outpace current manual processes",
        description=(
            "Leadership has publicly signalled growth and upcoming releases. Ambitions "
            "of this kind can move faster than the internal processes supporting them, "
            "which may increase manual work and inconsistency."
        ),
        rationale=(
            "Public growth commitments often precede operational strain."
        ),
        severity=Severity.MEDIUM,
    ),
    SignalType.OTHER: _Rule(
        title="Growing business activity may increase manual knowledge work",
        description=(
            "Recent activity suggests a growing business. Growth can increase manual, "
            "repetitive knowledge work that may benefit from automation or better "
            "internal knowledge access."
        ),
        rationale="General business growth is a soft indicator of rising manual work.",
        severity=Severity.LOW,
    ),
}

_SEVERITY_WEIGHT = {Severity.LOW: 0, Severity.MEDIUM: 1, Severity.HIGH: 2}


def _confidence(signal: Signal) -> float:
    score = 4.0 + max(signal.relevance_score, signal.source_quality_score) * 0.6
    return round(min(10.0, max(0.0, score)), 1)


def heuristic_problems(bundle: ResearchBundle) -> list[Problem]:
    """Deterministic rule-based problems derived from signals."""
    grouped: dict[SignalType, list[Signal]] = {}
    for signal in bundle.signals:
        grouped.setdefault(signal.signal_type, []).append(signal)

    problems: list[Problem] = []
    for signal_type, signals in grouped.items():
        rule = _RULES.get(signal_type)
        if rule is None:
            continue
        best = max(signals, key=lambda s: s.relevance_score)
        problems.append(
            Problem(
                title=rule.title,
                description=rule.description,
                rationale=rule.rationale,
                severity=rule.severity,
                confidence=_confidence(best),
                related_signals=[s.title for s in signals],
                source_urls=sorted({s.source_url for s in signals if s.source_url}),
            )
        )

    problems.sort(
        key=lambda p: (_SEVERITY_WEIGHT[p.severity], p.confidence), reverse=True
    )

    if not problems and bundle.evidence:
        evidence = max(bundle.evidence, key=lambda e: e.rank_score)
        problems.append(
            Problem(
                title="Manual research and data workflows may not scale with growth",
                description=(
                    "Public evidence suggests an active growing business. Growth can "
                    "increase the manual research and data work required per account, "
                    "which may create consistency and scalability challenges."
                ),
                rationale=(
                    "Derived from the strongest available evidence when no specific "
                    "signal rule applied."
                ),
                severity=Severity.LOW,
                confidence=4.0,
                related_signals=[],
                source_urls=[evidence.url] if evidence.url else [],
            )
        )

    return problems[:MAX_PROBLEMS]


SYSTEM_PROMPT = """You are a careful B2B sales analyst.

You must infer plausible BUSINESS PROBLEMS for a prospect company using ONLY the
supplied signals and evidence. These are HYPOTHESES, not facts.

Rules:
1. Use ONLY the supplied signals/evidence. Never invent facts, numbers or sources.
2. Phrase every problem tentatively ("may", "could", "often"), never as a certainty.
3. `source_urls` MUST be copied verbatim from the supplied signals. If no URL
   supports a problem, leave `source_urls` empty.
4. `related_signals` should list the exact titles of the signals used.
5. `severity` MUST be one of: LOW, MEDIUM, HIGH.
6. `confidence` is a 0-10 number.
7. Return at most 4 of the strongest, most specific problems.

Respond with ONLY a JSON object:
{
  "problems": [
    {
      "title": "short headline",
      "description": "two or three tentative sentences",
      "rationale": "why this is inferred",
      "severity": "MEDIUM",
      "confidence": 7.5,
      "related_signals": ["signal title"],
      "source_urls": ["https://..."]
    }
  ]
}"""


def _build_user_prompt(
    prospect: ProspectInput, bundle: ResearchBundle
) -> str:
    lines = [f"Prospect company: {prospect.company}"]
    if prospect.job_title:
        lines.append(f"Prospect title: {prospect.job_title}")
    lines.append("")
    lines.append(f"SIGNALS ({len(bundle.signals)}):")
    for index, signal in enumerate(bundle.signals, start=1):
        lines.append(
            f"[{index}] type={signal.signal_type.value} | {signal.title}\n"
            f"    {signal.description}\n"
            f"    source_url: {signal.source_url}"
        )
    if not bundle.signals:
        lines.append("(no signals; base inference only on the evidence below)")
    lines.append("")
    lines.append(f"EVIDENCE ({len(bundle.evidence)}):")
    for index, item in enumerate(bundle.evidence, start=1):
        lines.append(f"[{index}] {item.title} | {item.url}")
    lines.append("")
    lines.append("Infer at most 4 supported business problems as JSON.")
    return "\n".join(lines)


async def llm_problems(
    prospect: ProspectInput,
    bundle: ResearchBundle,
    llm: LLMProvider,
) -> list[Problem]:
    raw = await llm.complete_json(SYSTEM_PROMPT, _build_user_prompt(prospect, bundle))

    if isinstance(raw, dict):
        raw_problems = raw.get("problems", [])
    elif isinstance(raw, list):
        raw_problems = raw
    else:
        raise LLMError("Problem evaluation returned an unexpected JSON shape.")
    if not isinstance(raw_problems, list):
        raise LLMError("Problem evaluation: 'problems' was not a list.")

    allowed_urls = {s.source_url for s in bundle.signals if s.source_url}
    allowed_urls |= {e.url for e in bundle.evidence if e.url}

    problems: list[Problem] = []
    for item in raw_problems:
        if not isinstance(item, dict):
            continue
        urls = [
            str(url).strip()
            for url in item.get("source_urls", [])
            if str(url).strip() in allowed_urls
        ]
        try:
            problems.append(
                Problem(
                    title=str(item.get("title", "")).strip() or "Untitled problem",
                    description=str(item.get("description", "")).strip(),
                    rationale=str(item.get("rationale", "")).strip(),
                    severity=str(item.get("severity", "MEDIUM")).strip().upper(),
                    confidence=float(item.get("confidence", 5.0)),
                    related_signals=[
                        str(t).strip() for t in item.get("related_signals", [])
                    ],
                    source_urls=sorted(set(urls)),
                )
            )
        except Exception as exc:  # noqa: BLE001 - skip a single malformed problem
            logger.warning("Discarding invalid problem: %s", exc)

    return problems[:MAX_PROBLEMS]


async def evaluate_problems(
    prospect: ProspectInput,
    bundle: ResearchBundle,
    llm: LLMProvider | None,
    *,
    prefer_llm: bool,
) -> tuple[list[Problem], bool]:
    """Return (problems, used_llm).

    Falls back to the heuristic engine whenever the LLM is unavailable or fails.
    """
    if prefer_llm and llm is not None:
        try:
            problems = await llm_problems(prospect, bundle, llm)
            if problems:
                return problems, True
            logger.warning("LLM returned no problems; using heuristic fallback.")
        except LLMError as exc:
            logger.warning("LLM problem evaluation failed: %s", exc.message)
        except Exception as exc:  # noqa: BLE001
            logger.warning("Unexpected problem-evaluation error: %s", exc)

    return heuristic_problems(bundle), False
