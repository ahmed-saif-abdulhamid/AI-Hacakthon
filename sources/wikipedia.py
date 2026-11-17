"""Wikipedia summary: market context only, never pain evidence.

The first search result is often unrelated (searching "freelancers" finds a 2003 video game), so
code checks relevance before anything is shown: the article must share at least two specific
keywords with the segment and job, and must not be a list, disambiguation or media page.
Otherwise there is no background section at all.
"""

from __future__ import annotations

import re
import time

from .base import DEFAULT_TIMEOUT_SECONDS, FETCH_ERRORS, get_json, keywords, normalize

SOURCE = "wikipedia"
SEARCH_RESULTS = 5
MIN_SHARED_KEYWORDS = 2
SKIP_TEXT_PROBE_CHARS = 300
MAX_EXTRACT_CHARS = 600
SKIP_TITLE = re.compile(
    r"^(list of|lists of|index of|outline of)\b|\((video game|film|tv series|album|song|band|"
    r"novel|disambiguation|magazine|company)\)",
    re.I,
)
SKIP_TEXT = re.compile(r"\b(may refer to|is a \d{4} (video game|film|novel|album)|video game developed by)\b", re.I)


def relevant(title: str, extract: str, topic: set[str]) -> bool:
    if SKIP_TITLE.search(title) or SKIP_TEXT.search(extract[:SKIP_TEXT_PROBE_CHARS]):
        return False
    return len(keywords(title + " " + extract) & topic) >= MIN_SHARED_KEYWORDS


def context(
    segment: str, lang: str = "en", timeout: float = DEFAULT_TIMEOUT_SECONDS, topic: set[str] | None = None
) -> dict | None:
    """The first relevant article summary for ``segment``, or None (none relevant, or Wikipedia unreachable)."""
    t0 = time.time()
    base = "https://" + lang + ".wikipedia.org"
    topic = topic or keywords(segment)
    try:
        for title in _search_titles(base, segment, timeout):
            summary = get_json(base + "/api/rest_v1/page/summary/" + title.replace(" ", "_"), SOURCE, timeout=timeout)
            if summary.get("type") == "disambiguation":
                continue
            extract = normalize(summary.get("extract", ""))
            if relevant(title, extract, topic):
                return {
                    "title": title,
                    "url": summary.get("content_urls", {}).get("desktop", {}).get("page", ""),
                    "extract": extract[:MAX_EXTRACT_CHARS],
                    "seconds": round(time.time() - t0, 2),
                }
    except FETCH_ERRORS:
        return None
    return None


def _search_titles(base: str, segment: str, timeout: float) -> list[str]:
    params = {"action": "query", "list": "search", "srsearch": segment, "format": "json", "srlimit": SEARCH_RESULTS}
    data = get_json(base + "/w/api.php", SOURCE, params=params, timeout=timeout)
    results = data.get("query", {}).get("search", [])[:SEARCH_RESULTS]
    return [r["title"] for r in results if r.get("title")]
