"""Company website fetcher (priority source #1)."""

from __future__ import annotations

from app.config import Settings
from app.logging_config import get_logger
from app.models.research import SearchResult
from app.research.classify import classify_source
from app.utils.text import canonical_url, domain_of, html_to_text

logger = get_logger(__name__)


class WebsiteFetcher:
    def __init__(self, settings: Settings) -> None:
        self.timeout = settings.request_timeout

    async def fetch(self, url: str) -> SearchResult | None:
        """Fetch and extract readable text from a company page.

        Returns None (rather than raising) on failure so that a single bad URL
        does not break the whole research run.
        """
        import httpx

        headers = {
            "User-Agent": (
                "Mozilla/5.0 (compatible; NorthstarResearchBot/0.1; "
                "+https://example.invalid/bot)"
            )
        }
        try:
            async with httpx.AsyncClient(
                timeout=self.timeout, follow_redirects=True, headers=headers
            ) as client:
                response = await client.get(url)
                response.raise_for_status()
        except httpx.HTTPError as exc:
            logger.warning("Website fetch failed for %s: %s", url, exc)
            return None

        content_type = response.headers.get("content-type", "")
        if "html" not in content_type and "text" not in content_type:
            logger.info("Skipping non-HTML company page: %s (%s)", url, content_type)
            return None

        text = html_to_text(response.text)
        if not text:
            return None

        domain = domain_of(str(response.url))
        return SearchResult(
            title=f"{domain} — company website",
            url=canonical_url(str(response.url)) or url,
            content=text,
            source_name=domain,
            source_type=classify_source(str(response.url), company_domain=domain),
            query="company website",
        )
