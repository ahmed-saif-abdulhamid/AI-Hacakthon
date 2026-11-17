"""Stack Exchange advanced search (free; an optional free SE_KEY raises the daily quota)."""

from __future__ import annotations

import os
import time

from proveit.models import Hit, SourceCall

from .base import DEFAULT_TIMEOUT_SECONDS, FETCH_ERRORS, Source, make_hit, ts_to_dt

API = "https://api.stackexchange.com/2.3/search/advanced"
DEFAULT_SITE = "softwareengineering"
RESULTS_PER_SEARCH = 10


class StackExchange(Source):
    name = "stackexchange"
    pain_capable = True

    def search(
        self, query: str, site: str = DEFAULT_SITE, timeout: float = DEFAULT_TIMEOUT_SECONDS, **kw
    ) -> tuple[list[Hit], SourceCall]:
        t0 = time.time()
        label = f"{query} @ {site}"
        params = {
            "q": query,
            "site": site,
            "sort": "relevance",
            "order": "desc",
            "pagesize": RESULTS_PER_SEARCH,
            "filter": "withbody",
        }
        if os.environ.get("SE_KEY"):
            params["key"] = os.environ["SE_KEY"]
        try:
            data = self._get_json(API, params=params, timeout=timeout)
        except FETCH_ERRORS as e:
            return [], self._failed(label, API, t0, e)
        hits = [
            make_hit(
                "stackexchange",
                it.get("link", ""),
                it.get("title", "") + ". " + (it.get("body") or ""),
                title=it.get("title", ""),
                published_at=ts_to_dt(it.get("creation_date")),
                engagement=it.get("view_count"),
                query=query,
            )
            for it in data.get("items", [])
        ]
        return hits, self._call(label, API, t0, hits)
