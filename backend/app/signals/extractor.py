"""LLM-based business signal extraction (structured output)."""

from __future__ import annotations

import json

from app.errors import LLMError
from app.llm.base import LLMProvider
from app.logging_config import get_logger
from app.models.prospect import ProspectInput
from app.models.research import Evidence
from app.models.signal import Signal, SignalType

logger = get_logger(__name__)

_SIGNAL_TYPES = ", ".join(t.value for t in SignalType)

SYSTEM_PROMPT = f"""You are a meticulous B2B sales research analyst.

Your job: extract CONCRETE business signals from the PUBLIC EVIDENCE supplied by
the user. You are given only evidence that was actually retrieved from public
sources. You must operate strictly within it.

Rules:
1. Use ONLY the supplied evidence. Never invent facts, dates, numbers or sources.
2. Every signal MUST copy a real `source_name` and `source_url` from the evidence.
3. `evidence` MUST be a short, near-verbatim excerpt from that source.
4. `signal_type` MUST be exactly one of: {_SIGNAL_TYPES}.
5. Do NOT infer problems or opinions here — only report observable signals.
6. If nothing meaningful is supported for a signal, omit it. It is fine to
   return fewer signals, even zero.

Respond with ONLY a JSON object of this exact shape:
{{
  "signals": [
    {{
      "signal_type": "HIRING",
      "title": "short headline",
      "description": "one or two factual sentences",
      "source_name": "techcrunch.com",
      "source_url": "https://...",
      "published_date": "YYYY-MM-DD or null",
      "evidence": "near-verbatim excerpt",
      "recency_score": 0-10,
      "source_quality_score": 0-10,
      "relevance_score": 0-10
    }}
  ]
}}"""


def _build_user_prompt(prospect: ProspectInput, evidence: list[Evidence]) -> str:
    lines = [
        f"Prospect company: {prospect.company}",
        f"Company URL: {prospect.company_url or 'unknown'}",
    ]
    if prospect.job_title:
        lines.append(f"Prospect title: {prospect.job_title}")
    lines.append("")
    lines.append(f"PUBLIC EVIDENCE ({len(evidence)} items):")

    for index, item in enumerate(evidence, start=1):
        excerpt = item.content[:700]
        lines.append(
            "\n".join(
                [
                    f"[{index}] title: {item.title}",
                    f"    source_name: {item.source_name}",
                    f"    source_url: {item.url}",
                    f"    published_date: {item.published_date or 'unknown'}",
                    f"    content: {excerpt}",
                ]
            )
        )

    lines.append("")
    lines.append("Extract the strongest supported business signals as JSON.")
    return "\n".join(lines)


async def extract_signals(
    prospect: ProspectInput,
    evidence: list[Evidence],
    llm: LLMProvider,
) -> list[Signal]:
    if not evidence:
        return []

    raw = await llm.complete_json(
        SYSTEM_PROMPT, _build_user_prompt(prospect, evidence)
    )

    if isinstance(raw, dict):
        raw_signals = raw.get("signals", [])
    elif isinstance(raw, list):
        raw_signals = raw
    else:
        raise LLMError("Signal extraction returned an unexpected JSON shape.")

    if not isinstance(raw_signals, list):
        raise LLMError("Signal extraction: 'signals' was not a list.")

    by_url = {e.url: e for e in evidence}
    by_canonical = {e.url.rstrip("/"): e for e in evidence}

    signals: list[Signal] = []
    for item in raw_signals:
        if not isinstance(item, dict):
            continue
        # Never trust an LLM-provided source: require it to match real evidence.
        source_url = str(item.get("source_url", "")).strip()
        match = by_url.get(source_url) or by_canonical.get(source_url.rstrip("/"))
        if match is None:
            logger.warning(
                "Discarding signal with unverifiable source URL: %r", source_url
            )
            continue

        try:
            signals.append(
                Signal(
                    signal_type=item.get("signal_type", "OTHER"),
                    title=item.get("title") or match.title,
                    description=item.get("description", ""),
                    source_name=match.source_name or item.get("source_name", ""),
                    source_url=match.url,
                    published_date=match.published_date,
                    retrieved_date=match.retrieved_date,
                    evidence=item.get("evidence") or match.content[:300],
                    recency_score=match.recency_score,
                    source_quality_score=match.source_quality_score,
                    relevance_score=match.relevance_score,
                )
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning("Discarding invalid signal: %s", exc)

    # de-duplicate identical signals (same type + source)
    seen: set[tuple[str, str, str]] = set()
    unique: list[Signal] = []
    for signal in signals:
        key = (signal.signal_type.value, signal.source_url, signal.title.lower())
        if key in seen:
            continue
        seen.add(key)
        unique.append(signal)

    logger.info("Extracted %s signals from %s evidence items", len(unique), len(evidence))
    return unique
