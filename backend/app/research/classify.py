"""Classify research sources and assign base quality scores.

Implements the source priority from the specification:
  1. Company's own website
  2. Company newsroom / blog / press release
  3. Company careers page
  4. Official executive/company public posts
  5. Reputable news publications
  6. Other relevant sources
"""

from __future__ import annotations

from app.models.research import SourceType
from app.utils.text import domain_of

_NEWS_DOMAINS = {
    "techcrunch.com", "reuters.com", "bloomberg.com", "forbes.com", "cnbc.com",
    "businessinsider.com", "venturebeat.com", "axios.com", "wsj.com", "ft.com",
    "theverge.com", "businesswire.com", "prnewswire.com", "globenewswire.com",
    "finance.yahoo.com", "marketwatch.com", "fortune.com", "entrepreneur.com",
    "inc.com", "zdnet.com", "computerworld.com", "infoworld.com",
}

_SOCIAL_DOMAINS = {"x.com", "twitter.com"}

_QUALITY_BY_SOURCE: dict[SourceType, float] = {
    SourceType.COMPANY_WEBSITE: 10.0,
    SourceType.COMPANY_NEWSROOM: 9.0,
    SourceType.COMPANY_CAREERS: 8.0,
    SourceType.EXECUTIVE_POST: 7.0,
    SourceType.NEWS_PUBLICATION: 6.0,
    SourceType.OTHER: 4.0,
}

_CAREERS_HINTS = ("career", "jobs", "job/", "/join", "hiring", "work-with-us")
_NEWSROOM_HINTS = (
    "news", "newsroom", "press", "blog", "mediaroom", "investor",
    "announcement", "updates",
)


def classify_source(url: str, *, company_domain: str | None) -> SourceType:
    domain = domain_of(url)
    if not domain:
        return SourceType.OTHER

    path = url.lower()

    if company_domain and (domain == company_domain or domain.endswith("." + company_domain)):
        if any(hint in path for hint in _CAREERS_HINTS):
            return SourceType.COMPANY_CAREERS
        if any(hint in path for hint in _NEWSROOM_HINTS):
            return SourceType.COMPANY_NEWSROOM
        return SourceType.COMPANY_WEBSITE

    # subdomains commonly used by company blogs / newsrooms
    root = domain.split(".")[-2] if domain.count(".") >= 2 else domain
    if company_domain and root and root in company_domain:
        if any(hint in path for hint in _CAREERS_HINTS):
            return SourceType.COMPANY_CAREERS
        if any(hint in path for hint in _NEWSROOM_HINTS):
            return SourceType.COMPANY_NEWSROOM

    if domain in _SOCIAL_DOMAINS:
        return SourceType.EXECUTIVE_POST
    if domain in _NEWS_DOMAINS:
        return SourceType.NEWS_PUBLICATION
    return SourceType.OTHER


def quality_score(source_type: SourceType) -> float:
    return _QUALITY_BY_SOURCE.get(source_type, 4.0)
