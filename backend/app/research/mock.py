"""Mock research loader.

Enables a completely offline, end-to-end demonstration: no Tavily, no website
fetching, no X. Mock files live in `northstar/mock/` (see spec section 14).
"""

from __future__ import annotations

import json
from pathlib import Path

from app.config import Settings
from app.errors import ResearchError
from app.logging_config import get_logger
from app.models.prospect import ProspectInput
from app.models.research import SearchResult, utc_now_iso
from app.models.signal import Signal

logger = get_logger(__name__)


def _candidate_paths(prospect: ProspectInput, settings: Settings) -> list[Path]:
    slug = prospect.company_slug
    return [
        settings.mock_dir / f"{slug}_research.json",
        settings.mock_dir / f"{slug}.json",
        settings.mock_dir / "default_research.json",
    ]


def load_mock_research(
    prospect: ProspectInput, settings: Settings
) -> tuple[list[SearchResult], list[Signal], list[str], str | None]:
    """Load mock results + signals for a prospect.

    Returns (results, signals, queries, notes). Raises ResearchError when no
    mock file can be found so the API can return a helpful message.
    """
    path = next((p for p in _candidate_paths(prospect, settings) if p.is_file()), None)
    if path is None:
        searched = "\n".join(f"  - {p}" for p in _candidate_paths(prospect, settings))
        raise ResearchError(
            "No mock research file found for this company and RESEARCH_MODE=mock.",
            detail=(
                f"Add a mock file for '{prospect.company_slug}' or switch to "
                f"RESEARCH_MODE=live.\nSearched:\n{searched}"
            ),
        )

    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ResearchError(f"Could not read mock file {path.name}.", detail=str(exc)) from exc

    retrieved = data.get("retrieved_date") or utc_now_iso()

    results: list[SearchResult] = []
    for raw in data.get("results", []):
        try:
            results.append(
                SearchResult(
                    title=raw.get("title", ""),
                    url=raw.get("url", ""),
                    content=raw.get("content", ""),
                    source_name=raw.get("source_name", ""),
                    source_type=raw.get("source_type", "OTHER"),
                    published_date=raw.get("published_date"),
                    retrieved_date=raw.get("retrieved_date") or retrieved,
                    query=raw.get("query"),
                )
            )
        except Exception as exc:  # noqa: BLE001 - skip a single malformed mock row
            logger.warning("Skipping malformed mock result in %s: %s", path.name, exc)

    signals: list[Signal] = []
    for raw in data.get("signals", []):
        try:
            payload = dict(raw)
            payload.setdefault("retrieved_date", retrieved)
            signals.append(Signal(**payload))
        except Exception as exc:  # noqa: BLE001
            logger.warning("Skipping malformed mock signal in %s: %s", path.name, exc)

    queries = data.get("queries", [])
    notes = data.get("notes")
    logger.info(
        "Loaded mock research '%s': %s results, %s signals",
        path.name,
        len(results),
        len(signals),
    )
    return results, signals, queries, notes
