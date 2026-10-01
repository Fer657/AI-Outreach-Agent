"""Relevance / recency / source-quality ranking of research evidence."""

from __future__ import annotations

from app.config import Settings
from app.models.prospect import ProspectInput
from app.models.research import Evidence, SearchResult
from app.research.classify import quality_score
from app.utils.text import days_since, tokenize

SIGNAL_KEYWORDS: set[str] = {
    "funding", "fundraise", "raised", "raise", "series", "investment",
    "investor", "valuation", "seed", "round",
    "hiring", "hire", "hires", "careers", "career", "jobs", "recruit",
    "expanding", "expansion", "expand", "newmarket", "office", "region",
    "partnership", "partner", "partners", "collaboration", "alliance",
    "launch", "launches", "launched", "release", "unveil", "announce",
    "acquisition", "acquires", "acquired", "merger", "merges",
    "appoint", "appointed", "ceo", "cto", "cfo", "leadership", "executive",
    "growth", "growing", "revenue", "customers", "customer", "integration",
    "platform", "technology", "product", "empower", "scale", "scaling",
}

# rank weighting (must sum to 1.0)
W_RELEVANCE = 0.40
W_QUALITY = 0.35
W_RECENCY = 0.25

MIN_RELEVANCE = 2.5
STALE_DAYS = 730  # 2 years


def _relevance(result: SearchResult, prospect: ProspectInput) -> tuple[float, str]:
    targets = tokenize(prospect.company)
    if prospect.job_title:
        targets |= tokenize(prospect.job_title)
    if result.query:
        targets |= tokenize(result.query)

    haystack = tokenize(f"{result.title} {result.content}")
    title_tokens = tokenize(result.title)

    company_hits = targets & haystack
    signal_hits = SIGNAL_KEYWORDS & haystack
    title_signal_hits = SIGNAL_KEYWORDS & title_tokens

    score = 1.0
    reasons: list[str] = []

    if company_hits:
        score += 3.0 + min(len(company_hits), 2) * 0.5
        reasons.append(f"matches company/query terms ({', '.join(sorted(company_hits)[:3])})")

    if signal_hits:
        score += min(len(signal_hits), 6) * 0.8
        reasons.append(f"business-signal terms ({len(signal_hits)})")

    if title_signal_hits:
        score += 0.75
        reasons.append("signal term in title")

    score = round(min(score, 10.0), 1)
    rationale = "; ".join(reasons) if reasons else "no clear company or signal terms"
    return score, rationale


def _recency(result: SearchResult) -> tuple[float, str]:
    age = days_since(result.published_date)
    if age is None:
        return 5.0, "no publication date available"
    if age <= 30:
        return 10.0, f"published {age}d ago"
    if age <= 90:
        return 8.0, f"published {age}d ago"
    if age <= 180:
        return 6.0, f"published {age}d ago"
    if age <= 365:
        return 4.0, f"published {age}d ago"
    if age <= STALE_DAYS:
        return 2.0, f"published {age}d ago (aging)"
    return 1.0, f"published {age}d ago (stale)"


def score_and_select(
    results: list[SearchResult],
    prospect: ProspectInput,
    settings: Settings,
) -> tuple[list[Evidence], int]:
    """Score results and return the strongest evidence plus filtered-out count."""
    scored: list[Evidence] = []
    filtered_out = 0

    for result in results:
        relevance, relevance_reason = _relevance(result, prospect)
        if relevance < MIN_RELEVANCE:
            filtered_out += 1
            continue

        recency, recency_reason = _recency(result)
        quality = quality_score(result.source_type)
        rank = round(
            W_RELEVANCE * relevance + W_QUALITY * quality + W_RECENCY * recency, 2
        )

        scored.append(
            Evidence(
                **result.model_dump(),
                relevance_score=relevance,
                recency_score=recency,
                source_quality_score=quality,
                rank_score=rank,
                rationale=f"relevance: {relevance_reason}; recency: {recency_reason}",
            )
        )

    scored.sort(key=lambda e: e.rank_score, reverse=True)
    selected = scored[: settings.max_evidence]
    return selected, filtered_out
