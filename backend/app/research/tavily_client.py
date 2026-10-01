"""Tavily Search API client."""

from __future__ import annotations

import httpx

from app.config import Settings
from app.errors import ConfigError, SearchAPIError
from app.logging_config import get_logger
from app.models.prospect import ProspectInput
from app.models.research import SearchResult
from app.research.classify import classify_source
from app.utils.text import domain_of

logger = get_logger(__name__)


class TavilyClient:
    def __init__(self, settings: Settings) -> None:
        if not settings.tavily_api_key:
            raise ConfigError(
                "TAVILY_API_KEY is not set. Add it to backend/.env or use "
                "RESEARCH_MODE=mock."
            )
        self.api_key = settings.tavily_api_key
        self.base_url = settings.tavily_base_url.rstrip("/")
        self.timeout = settings.request_timeout
        self.max_results = settings.top_k_per_query

    async def search(self, query: str, prospect: ProspectInput) -> list[SearchResult]:
        company_domain = domain_of(prospect.company_url) if prospect.company_url else None
        payload = {
            "api_key": self.api_key,
            "query": query,
            "max_results": self.max_results,
            "search_depth": "basic",
            "topic": "general",
            "include_answer": False,
            "include_raw_content": False,
        }

        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.post(f"{self.base_url}/search", json=payload)
        except httpx.TimeoutException as exc:
            raise SearchAPIError(
                f"Tavily timed out after {self.timeout}s for query: {query!r}",
                detail=str(exc),
            ) from exc
        except httpx.HTTPError as exc:
            raise SearchAPIError("Tavily request failed.", detail=str(exc)) from exc

        if response.status_code == 401:
            raise SearchAPIError("Tavily authentication failed (check TAVILY_API_KEY).")
        if response.status_code == 429:
            raise SearchAPIError("Tavily rate limit reached. Try again shortly.")
        if response.status_code >= 400:
            raise SearchAPIError(
                f"Tavily returned HTTP {response.status_code}.",
                detail=response.text[:300],
            )

        data = response.json()
        results: list[SearchResult] = []
        for item in data.get("results", []):
            url = item.get("url") or ""
            if not url:
                continue
            results.append(
                SearchResult(
                    title=(item.get("title") or url).strip(),
                    url=url,
                    content=(item.get("content") or "").strip(),
                    source_name=domain_of(url),
                    source_type=classify_source(url, company_domain=company_domain),
                    published_date=item.get("published_date"),
                    query=query,
                )
            )
        logger.info("Tavily: %s results for %r", len(results), query)
        return results
