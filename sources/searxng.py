"""SearXNG metasearch (self-hosted container). Snippets are not evidence: the top result
pages are fetched and their text is split into sentences."""
from __future__ import annotations

import os
import time

import httpx

from .base import USER_AGENT, Source, get_json, make_hit, normalize


class SearXNG(Source):
    name = "searxng"
    pain_capable = True

    def __init__(self, base_url: str | None = None):
        self.base_url = (base_url or os.environ.get("SEARXNG_URL") or "http://localhost:8080").rstrip("/")

    def search(self, query: str, language: str = "en", fetch: int = 4, timeout: float = 8.0, **kw):
        t0 = time.time()
        url = self.base_url + "/search"
        try:
            data = get_json(url, params={"q": query, "format": "json", "language": language}, timeout=timeout)
        except Exception as e:  # noqa: BLE001
            return [], self._call(query, url, t0, error="unavailable: " + str(e)[:140])
        hits = []
        for res in data.get("results", [])[:fetch]:
            link = res.get("url")
            if not link:
                continue
            try:
                r = httpx.get(link, headers={"User-Agent": USER_AGENT}, timeout=timeout, follow_redirects=True)
                if r.status_code != 200 or "html" not in r.headers.get("content-type", ""):
                    continue
                text = normalize(r.text)[:20000]
            except Exception:  # noqa: BLE001
                continue
            hits.append(make_hit("web", link, text, title=res.get("title", ""), query=query, lang=language))
        return hits, self._call(query, url, t0, hits)
