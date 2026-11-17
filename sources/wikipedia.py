"""Wikipedia summary: market context only, never pain evidence.

The first search result is often unrelated (searching "freelancers" finds a 2003 video game), so
code checks relevance before anything is shown: the article must share at least two specific
keywords with the segment and job, and must not be a list, disambiguation or media page.
Otherwise there is no background section at all.
"""

from __future__ import annotations

import re
import time

from .base import get_json, keywords, normalize

SKIP_TITLE = re.compile(
    r"^(list of|lists of|index of|outline of)\b|\((video game|film|tv series|album|song|band|"
    r"novel|disambiguation|magazine|company)\)",
    re.I,
)
SKIP_TEXT = re.compile(r"\b(may refer to|is a \d{4} (video game|film|novel|album)|video game developed by)\b", re.I)


def relevant(title: str, extract: str, topic: set[str]) -> bool:
    if SKIP_TITLE.search(title) or SKIP_TEXT.search(extract[:300]):
        return False
    return len(keywords(title + " " + extract) & topic) >= 2


def context(segment: str, lang: str = "en", timeout: float = 8.0, topic: set[str] | None = None) -> dict | None:
    t0 = time.time()
    base = "https://" + lang + ".wikipedia.org"
    topic = topic or keywords(segment)
    try:
        data = get_json(
            base + "/w/api.php",
            params={"action": "query", "list": "search", "srsearch": segment, "format": "json", "srlimit": 5},
            timeout=timeout,
        )
        for res in data.get("query", {}).get("search", [])[:5]:
            title = res["title"]
            summ = get_json(base + "/api/rest_v1/page/summary/" + title.replace(" ", "_"), timeout=timeout)
            if summ.get("type") == "disambiguation":
                continue
            extract = normalize(summ.get("extract", ""))
            if not relevant(title, extract, topic):
                continue
            return {
                "title": title,
                "url": summ.get("content_urls", {}).get("desktop", {}).get("page", ""),
                "extract": extract[:600],
                "seconds": round(time.time() - t0, 2),
            }
        return None
    except Exception:  # noqa: BLE001
        return None
