"""TinyFish research client (search + fetch).

TinyFish exposes two free, key-authenticated endpoints that cover the two
research sources this app needs:

  * Search  GET  https://api.search.tinyfish.ai?query=...   -> ranked web results
  * Fetch   POST https://api.fetch.tinyfish.ai              -> clean page content

Auth is a single `X-API-Key` header. Both endpoints never draw from the wallet,
but the account still needs Search API access.
"""

from __future__ import annotations

import httpx

from app.config import Settings
from app.errors import ConfigError, SearchAPIError
from app.logging_config import get_logger
from app.models.prospect import ProspectInput
from app.models.research import SearchResult
from app.research.classify import classify_source
from app.utils.text import canonical_url, domain_of

logger = get_logger(__name__)

_PURPOSE = (
    "Research a B2B sales prospect: recent company news, growth/hiring signals, "
    "executive statements, and business context for personalized outreach."
)
_FETCH_MAX_CHARS = 6000


class TinyFishClient:
    """Search and Fetch adapter for TinyFish.

    Exposes the same `search` contract as `TavilyClient` plus a `fetch` method
    that mirrors `WebsiteFetcher.fetch`, so the research service can use it for
    both sources.
    """

    def __init__(self, settings: Settings) -> None:
        if not settings.tinyfish_api_key:
            raise ConfigError(
                "TINYFISH_API_KEY is not set. Add it to backend/.env or use "
                "RESEARCH_MODE=mock."
            )
        self.api_key = settings.tinyfish_api_key
        self.search_url = settings.tinyfish_search_url.rstrip("/")
        self.fetch_url = settings.tinyfish_fetch_url.rstrip("/")
        self.location = settings.tinyfish_location
        self.language = settings.tinyfish_language
        self.timeout = settings.request_timeout
        self.max_results = settings.top_k_per_query

    # ----- search -----------------------------------------------------------
    async def search(self, query: str, prospect: ProspectInput) -> list[SearchResult]:
        company_domain = domain_of(prospect.company_url) if prospect.company_url else None
        params = {
            "query": query,
            "purpose": _PURPOSE,
            "location": self.location,
            "language": self.language,
        }
        headers = {"X-API-Key": self.api_key}

        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.get(
                    self.search_url, params=params, headers=headers
                )
        except httpx.TimeoutException as exc:
            raise SearchAPIError(
                f"TinyFish timed out after {self.timeout}s for query: {query!r}",
                detail=str(exc),
            ) from exc
        except httpx.HTTPError as exc:
            raise SearchAPIError("TinyFish search request failed.", detail=str(exc)) from exc

        self._raise_for_status(response, action="search")

        try:
            data = response.json()
        except ValueError as exc:
            raise SearchAPIError("TinyFish returned a non-JSON response.", detail=str(exc)) from exc

        results: list[SearchResult] = []
        for item in data.get("results", [])[: self.max_results]:
            url = (item.get("url") or "").strip()
            if not url:
                continue
            results.append(
                SearchResult(
                    title=(item.get("title") or url).strip(),
                    url=url,
                    content=(item.get("snippet") or "").strip(),
                    source_name=item.get("site_name") or domain_of(url),
                    source_type=classify_source(url, company_domain=company_domain),
                    published_date=item.get("date"),
                    query=query,
                )
            )
        logger.info("TinyFish search: %s results for %r", len(results), query)
        return results

    # ----- fetch ------------------------------------------------------------
    async def fetch(self, url: str) -> SearchResult | None:
        """Fetch one page as clean markdown. Returns None on failure (never raises)."""
        headers = {"X-API-Key": self.api_key, "Content-Type": "application/json"}
        payload = {"urls": [url], "format": "markdown", "ttl": 0}

        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.post(self.fetch_url, json=payload, headers=headers)
        except httpx.HTTPError as exc:
            logger.warning("TinyFish fetch failed for %s: %s", url, exc)
            return None

        if response.status_code >= 400:
            logger.warning("TinyFish fetch HTTP %s for %s", response.status_code, url)
            return None

        try:
            data = response.json()
        except ValueError:
            return None

        for error in data.get("errors", []) or []:
            logger.info(
                "TinyFish fetch error for %s: %s",
                error.get("url", url),
                error.get("error", "unknown"),
            )

        pages = data.get("results", []) or []
        if not pages:
            return None

        page = pages[0]
        text = (page.get("text") or "").strip()
        if not text:
            return None

        final_url = page.get("final_url") or page.get("url") or url
        domain = domain_of(final_url)
        return SearchResult(
            title=(page.get("title") or f"{domain} — company website").strip(),
            url=canonical_url(final_url) or final_url,
            content=text[:_FETCH_MAX_CHARS],
            source_name=domain,
            source_type=classify_source(final_url, company_domain=domain),
            query="company website",
        )

    # ----- shared -----------------------------------------------------------
    def _raise_for_status(self, response: httpx.Response, *, action: str) -> None:
        if response.status_code < 400:
            return
        if response.status_code == 401:
            raise SearchAPIError("TinyFish authentication failed (check TINYFISH_API_KEY).")
        if response.status_code == 402:
            raise SearchAPIError(
                "TinyFish payment required: this account needs Search API access."
            )
        if response.status_code == 403:
            raise SearchAPIError(
                "TinyFish search request forbidden by the upstream service."
            )
        if response.status_code == 404:
            raise SearchAPIError("TinyFish Search API is not available for this account.")
        if response.status_code == 429:
            raise SearchAPIError("TinyFish rate limit reached. Try again shortly.")
        raise SearchAPIError(
            f"TinyFish {action} returned HTTP {response.status_code}.",
            detail=response.text[:300],
        )
