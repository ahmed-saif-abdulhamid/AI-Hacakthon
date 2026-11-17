"""SearXNG metasearch (self-hosted container). Snippets are not evidence: the top result
pages are fetched and their text is split into sentences."""

from __future__ import annotations

import os
import time

import httpx

from proveit.models import Hit, SourceCall

from .base import DEFAULT_TIMEOUT_SECONDS, FETCH_ERRORS, NETWORK_ERRORS, USER_AGENT, Source, make_hit, normalize

DEFAULT_URL = "http://localhost:8080"
DEFAULT_PAGES_FETCHED = 4
MAX_PAGE_CHARS = 20000


class SearXNG(Source):
    name = "searxng"
    pain_capable = True

    def __init__(self, base_url: str | None = None):
        self.base_url = (base_url or os.environ.get("SEARXNG_URL") or DEFAULT_URL).rstrip("/")

    def search(
        self,
        query: str,
        language: str = "en",
        fetch: int = DEFAULT_PAGES_FETCHED,
        timeout: float = DEFAULT_TIMEOUT_SECONDS,
        **kw,
    ) -> tuple[list[Hit], SourceCall]:
        t0 = time.time()
        url = self.base_url + "/search"
        try:
            data = self._get_json(url, params={"q": query, "format": "json", "language": language}, timeout=timeout)
        except FETCH_ERRORS as e:
            return [], self._failed(query, url, t0, e, prefix="unavailable: ")
        hits = []
        for res in data.get("results", [])[:fetch]:
            link = res.get("url")
            text = _page_text(link, timeout) if link else None
            if text is not None:
                hits.append(make_hit("web", link, text, title=res.get("title", ""), query=query, lang=language))
        return hits, self._call(query, url, t0, hits)


def _page_text(link: str, timeout: float) -> str | None:
    """The text of one result page, or None when it is unreachable or not HTML.

    Result pages are arbitrary third-party sites, so one failing page says nothing about SearXNG's
    health and does not count against its circuit breaker.
    """
    try:
        r = httpx.get(link, headers={"User-Agent": USER_AGENT}, timeout=timeout, follow_redirects=True)
    except NETWORK_ERRORS:
        return None
    if r.status_code != httpx.codes.OK or "html" not in r.headers.get("content-type", ""):
        return None
    return normalize(r.text)[:MAX_PAGE_CHARS]
