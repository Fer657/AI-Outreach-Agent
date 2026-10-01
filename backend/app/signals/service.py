"""Signal extraction service (mock-aware)."""

from __future__ import annotations

from app.llm.base import LLMProvider
from app.models.prospect import ProspectInput
from app.models.research import Evidence
from app.models.signal import Signal
from app.signals.extractor import extract_signals


async def build_signals(
    prospect: ProspectInput,
    evidence: list[Evidence],
    llm: LLMProvider | None,
    *,
    precomputed: list[Signal] | None = None,
) -> list[Signal]:
    """Return signals for the evidence.

    In mock mode, pre-computed signals shipped with the mock file are used so
    the demo works with no LLM at all. Otherwise the configured LLM performs
    structured extraction.
    """
    if precomputed is not None:
        return precomputed
    if llm is None:
        return []
    return await extract_signals(prospect, evidence, llm)
