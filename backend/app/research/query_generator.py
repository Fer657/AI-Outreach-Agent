"""Query generation for prospect research."""

from __future__ import annotations

from app.config import Settings
from app.models.prospect import ProspectInput

DEFAULT_TEMPLATES: tuple[str, ...] = (
    "{company} recent news",
    "{company} funding OR investment",
    "{company} hiring OR careers",
    "{company} expansion OR partnership",
    "{company} product launch",
)


def generate_queries(prospect: ProspectInput, settings: Settings) -> list[str]:
    """Produce ~5 targeted search queries for a company.

    The five default templates are always used; a prospect-specific query is
    added (and kept ahead of the weakest default) when a prospect name is known.
    """
    company = prospect.company
    queries = [template.format(company=company) for template in DEFAULT_TEMPLATES]

    prospect_query: str | None = None
    if prospect.prospect_name:
        prospect_query = f'"{prospect.prospect_name}" "{company}"'
    elif prospect.job_title:
        prospect_query = f'"{company}" "{prospect.job_title}"'

    limit = max(settings.max_queries, 1)
    if prospect_query:
        if len(queries) >= limit:
            queries = queries[: limit - 1]
        queries.append(prospect_query)

    # de-duplicate while preserving order
    seen: set[str] = set()
    unique: list[str] = []
    for query in queries[:limit]:
        key = query.lower()
        if key not in seen:
            seen.add(key)
            unique.append(query)
    return unique
