"""Small shared helpers (no external dependencies)."""

from __future__ import annotations

import re
from datetime import date, datetime, timezone
from html import unescape
from html.parser import HTMLParser
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse

_TRACKING_PARAMS = {
    "utm_source",
    "utm_medium",
    "utm_campaign",
    "utm_term",
    "utm_content",
    "gclid",
    "fbclid",
    "ref",
    "ref_src",
}

_STOPWORDS = {
    "the", "a", "an", "and", "or", "of", "to", "for", "in", "on", "at", "by",
    "with", "is", "are", "was", "were", "be", "been", "this", "that", "these",
    "those", "it", "its", "as", "from", "we", "our", "their", "has", "have",
    "had", "will", "would", "can", "could", "may", "might", "new", "inc",
    "ltd", "llc", "corp", "company",
}


class _TextExtractor(HTMLParser):
    _SKIP = {"script", "style", "noscript", "template", "svg"}

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self._parts: list[str] = []
        self._skip_depth = 0

    def handle_starttag(self, tag: str, attrs) -> None:  # type: ignore[no-untyped-def]
        if tag in self._SKIP:
            self._skip_depth += 1

    def handle_endtag(self, tag: str) -> None:
        if tag in self._SKIP and self._skip_depth:
            self._skip_depth -= 1

    def handle_data(self, data: str) -> None:
        if not self._skip_depth and data.strip():
            self._parts.append(data.strip())

    def text(self) -> str:
        return " ".join(self._parts)


def html_to_text(html: str, *, max_chars: int = 6000) -> str:
    parser = _TextExtractor()
    try:
        parser.feed(html)
    except Exception:  # noqa: BLE001 - malformed HTML should not crash research
        pass
    text = re.sub(r"\s+", " ", unescape(parser.text())).strip()
    return text[:max_chars]


def canonical_url(url: str) -> str:
    """Normalise a URL for dedupe: drop scheme, www, tracking params, fragment."""
    try:
        parsed = urlparse(url.strip())
    except ValueError:
        return url.strip().lower()

    netloc = parsed.netloc.lower().removeprefix("www.")
    path = parsed.path.rstrip("/")
    query = urlencode(
        [(k, v) for k, v in parse_qsl(parsed.query) if k.lower() not in _TRACKING_PARAMS]
    )
    return urlunparse(("", netloc, path, "", query, ""))


def domain_of(url: str) -> str:
    try:
        return urlparse(url).netloc.lower().removeprefix("www.")
    except ValueError:
        return ""


def tokenize(text: str) -> set[str]:
    words = re.findall(r"[a-z0-9]+", text.lower())
    return {w for w in words if len(w) > 2 and w not in _STOPWORDS}


_DATE_FORMATS = (
    "%Y-%m-%d",
    "%Y/%m/%d",
    "%d/%m/%Y",
    "%m/%d/%Y",
    "%B %d, %Y",
    "%b %d, %Y",
    "%d %B %Y",
    "%d %b %Y",
)


def parse_date(value: str | None) -> date | None:
    if not value:
        return None
    value = value.strip()
    # ISO datetime with timezone / time component
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).date()
    except ValueError:
        pass
    for fmt in _DATE_FORMATS:
        try:
            return datetime.strptime(value, fmt).date()
        except ValueError:
            continue
    return None


def days_since(value: str | None) -> int | None:
    parsed = parse_date(value)
    if parsed is None:
        return None
    today = datetime.now(timezone.utc).date()
    return max((today - parsed).days, 0)
