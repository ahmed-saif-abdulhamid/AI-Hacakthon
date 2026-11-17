"""Wikipedia summary: market context only, never pain evidence."""
from __future__ import annotations

import time

from .base import get_json, normalize


def context(segment: str, lang: str = "en", timeout: float = 8.0) -> dict | None:
    t0 = time.time()
    base = "https://" + lang + ".wikipedia.org"
    try:
        data = get_json(base + "/w/api.php", params={"action": "query", "list": "search", "srsearch": segment,
                                                   "format": "json", "srlimit": 1}, timeout=timeout)
        results = data.get("query", {}).get("search", [])
        if not results:
            return None
        title = results[0]["title"]
        summ = get_json(base + "/api/rest_v1/page/summary/" + title.replace(" ", "_"), timeout=timeout)
        return {"title": title, "url": summ.get("content_urls", {}).get("desktop", {}).get("page", ""),
                "extract": normalize(summ.get("extract", ""))[:600], "seconds": round(time.time() - t0, 2)}
    except Exception:  # noqa: BLE001
        return None
