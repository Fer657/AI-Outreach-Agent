"""Research orchestration: search -> dedupe -> filter -> rank -> signals.

Kept deterministic and readable; no autonomous agents.
"""

from __future__ import annotations

import asyncio

from app.config import Settings
from app.errors import NoResultsError, ResearchError
from app.llm.base import LLMProvider
from app.logging_config import get_logger
from app.models.prospect import ProspectInput
from app.models.research import ResearchBundle, ResearchStats, SearchResult
from app.models.signal import Signal
from app.research.dedupe import dedupe_results
from app.research.mock import load_mock_research
from app.research.query_generator import generate_queries
from app.research.ranker import score_and_select
from app.research.tavily_client import TavilyClient
from app.research.tinyfish_client import TinyFishClient
from app.research.website_fetcher import WebsiteFetcher
from app.research.x_client import XClient
from app.signals.service import build_signals

logger = get_logger(__name__)


class ResearchService:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    async def run(
        self, prospect: ProspectInput, llm: LLMProvider | None = None
    ) -> ResearchBundle:
        mock_signals: list[Signal] | None = None
        notes: str | None = None

        if self.settings.is_mock:
            results, mock_signals, mock_queries, notes = load_mock_research(
                prospect, self.settings
            )
            queries = mock_queries or generate_queries(prospect, self.settings)
        else:
            queries = generate_queries(prospect, self.settings)
            results = await self._live_search(prospect, queries)

        raw_count = len(results)
        unique, removed = dedupe_results(results)
        evidence, filtered_out = score_and_select(unique, prospect, self.settings)

        if not evidence:
            raise NoResultsError(
                f"Research for '{prospect.company}' returned no usable evidence.",
                detail=(
                    f"{raw_count} raw results, {removed} duplicates removed, "
                    f"{filtered_out} filtered as irrelevant."
                ),
            )

        signals = await build_signals(
            prospect,
            evidence,
            llm,
            precomputed=mock_signals if self.settings.is_mock else None,
        )

        stats = ResearchStats(
            queries_run=len(queries),
            raw_results=raw_count,
            after_dedupe=len(unique),
            after_filtering=len(unique) - filtered_out,
            selected_evidence=len(evidence),
        )

        bundle = ResearchBundle(
            company=prospect.company,
            company_url=prospect.company_url,
            mode=self.settings.research_mode,
            queries=queries,
            evidence=evidence,
            signals=signals,
            stats=stats,
        )
        logger.info(
            "Research complete for %s: %s evidence, %s signals",
            prospect.company,
            len(evidence),
            len(signals),
        )
        return bundle

    async def _live_search(
        self, prospect: ProspectInput, queries: list[str]
    ) -> list[SearchResult]:
        x_client = XClient(self.settings)

        tasks = []
        if self.settings.search_provider == "tinyfish":
            # TinyFish covers both search and (JS-rendering) page fetch.
            tinyfish = TinyFishClient(self.settings)  # raises ConfigError if key missing
            tasks.extend(tinyfish.search(query, prospect) for query in queries)
            if prospect.company_url:
                tasks.append(tinyfish.fetch(prospect.company_url))
        else:
            tavily = TavilyClient(self.settings)  # raises ConfigError if key missing
            tasks.extend(tavily.search(query, prospect) for query in queries)
            website = WebsiteFetcher(self.settings)
            if prospect.company_url:
                tasks.append(website.fetch(prospect.company_url))

        tasks.append(x_client.search(f'"{prospect.company}"', prospect))

        outcomes = await asyncio.gather(*tasks, return_exceptions=True)

        results: list[SearchResult] = []
        failures = 0
        for outcome in outcomes:
            if isinstance(outcome, BaseException):
                if isinstance(outcome, ResearchError):
                    failures += 1
                    logger.warning("Research source failed: %s", outcome.message)
                else:
                    logger.exception("Unexpected research error: %s", outcome)
                    failures += 1
                continue
            if outcome is None:
                continue
            if isinstance(outcome, list):
                results.extend(outcome)
            else:
                results.append(outcome)

        if not results and failures:
            raise ResearchError(
                "All live research sources failed.",
                detail=(
                    f"Check your {self.settings.search_provider} API key and network "
                    "connectivity, or use RESEARCH_MODE=mock."
                ),
            )
        return results
