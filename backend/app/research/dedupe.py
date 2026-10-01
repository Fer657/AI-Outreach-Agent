"""Evidence de-duplication."""

from __future__ import annotations

import re

from app.models.research import SearchResult
from app.utils.text import canonical_url


def _title_key(title: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", title.lower())[:60]


def dedupe_results(
    results: list[SearchResult],
) -> tuple[list[SearchResult], int]:
    """Remove duplicate URLs and near-duplicate (same-site, same-title) items.

    Returns the unique results and the number removed.
    """
    seen_urls: set[str] = set()
    seen_site_titles: set[tuple[str, str]] = set()
    unique: list[SearchResult] = []

    for result in results:
        url_key = canonical_url(result.url)
        if url_key and url_key in seen_urls:
            continue

        title_key = _title_key(result.title)
        site_key = (result.source_name or "", title_key)
        if title_key and site_key in seen_site_titles:
            continue

        if url_key:
            seen_urls.add(url_key)
        if title_key:
            seen_site_titles.add(site_key)
        unique.append(result)

    return unique, len(results) - len(unique)
