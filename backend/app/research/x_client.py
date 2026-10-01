"""X / Twitter adapter.

The specification explicitly forbids automated LinkedIn scraping and asks to use
X only where available/permitted. Accordingly:

  * If X_API_BEARER_TOKEN is configured we use the official X API v2.
  * Otherwise, if the user explicitly supplies a public post URL we fetch that
    ONE page (no crawling, no scraping of timelines).
  * Otherwise this source is a no-op.
"""

from __future__ import annotations

import httpx

from app.config import Settings
from app.logging_config import get_logger
from app.models.prospect import ProspectInput
from app.models.research import SearchResult, SourceType
from app.utils.text import canonical_url, domain_of, html_to_text

logger = get_logger(__name__)


class XClient:
    def __init__(self, settings: Settings) -> None:
        self.token = settings.x_api_bearer_token
        self.base_url = settings.x_api_base_url.rstrip("/")
        self.timeout = settings.request_timeout

    @property
    def available(self) -> bool:
        return bool(self.token)

    async def search(self, query: str, prospect: ProspectInput) -> list[SearchResult]:
        if self.available:
            return await self._api_search(query)
        if prospect.x_post_url:
            return await self._fetch_single_post(prospect.x_post_url)
        return []

    async def _api_search(self, query: str) -> list[SearchResult]:
        headers = {"Authorization": f"Bearer {self.token}"}
        params = {
            "query": f"{query} -is:retweet",
            "max_results": 10,
            "tweet.fields": "created_at,public_metrics,author_id",
            "expansions": "author_id",
            "user.fields": "name,username,verified",
        }
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.get(
                    f"{self.base_url}/tweets/search/recent",
                    headers=headers,
                    params=params,
                )
        except httpx.HTTPError as exc:
            logger.warning("X API request failed: %s", exc)
            return []

        if response.status_code == 401:
            logger.warning("X API authentication failed (check X_API_BEARER_TOKEN).")
            return []
        if response.status_code == 429:
            logger.warning("X API rate limit reached.")
            return []
        if response.status_code >= 400:
            logger.warning("X API HTTP %s", response.status_code)
            return []

        data = response.json()
        users = {u["id"]: u for u in data.get("includes", {}).get("users", [])}
        results: list[SearchResult] = []
        for tweet in data.get("data", []):
            author = users.get(tweet.get("author_id"), {})
            handle = author.get("username", "x")
            tweet_id = tweet["id"]
            results.append(
                SearchResult(
                    title=f"@{handle} on X",
                    url=f"https://x.com/{handle}/status/{tweet_id}",
                    content=tweet.get("text", ""),
                    source_name="x.com",
                    source_type=SourceType.EXECUTIVE_POST,
                    published_date=tweet.get("created_at"),
                    query=query,
                )
            )
        return results

    async def _fetch_single_post(self, url: str) -> list[SearchResult]:
        """Fetch one user-supplied public post. Best effort, never a crawl."""
        try:
            async with httpx.AsyncClient(timeout=self.timeout, follow_redirects=True) as client:
                response = await client.get(url)
                response.raise_for_status()
        except httpx.HTTPError as exc:
            logger.info("Could not fetch supplied X post %s: %s", url, exc)
            return []

        text = html_to_text(response.text)
        if not text:
            return []
        domain = domain_of(url) or "x.com"
        return [
            SearchResult(
                title="User-supplied X post",
                url=canonical_url(url),
                content=text,
                source_name=domain,
                source_type=SourceType.EXECUTIVE_POST,
                query="x_post_url",
            )
        ]
