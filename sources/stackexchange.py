"""Stack Exchange advanced search (free; an optional free SE_KEY raises the daily quota)."""

from __future__ import annotations

import os
import time

from .base import Source, get_json, make_hit, ts_to_dt

API = "https://api.stackexchange.com/2.3/search/advanced"


class StackExchange(Source):
    name = "stackexchange"
    pain_capable = True

    def search(self, query: str, site: str = "softwareengineering", timeout: float = 8.0, **kw):
        t0 = time.time()
        params = {"q": query, "site": site, "sort": "relevance", "order": "desc", "pagesize": 10, "filter": "withbody"}
        if os.environ.get("SE_KEY"):
            params["key"] = os.environ["SE_KEY"]
        try:
            data = get_json(API, params=params, timeout=timeout)
        except Exception as e:  # noqa: BLE001
            return [], self._call(f"{query} @ {site}", API, t0, error=str(e)[:160])
        hits = []
        for it in data.get("items", []):
            body = it.get("title", "") + ". " + (it.get("body") or "")
            hits.append(
                make_hit(
                    "stackexchange",
                    it.get("link", ""),
                    body,
                    title=it.get("title", ""),
                    published_at=ts_to_dt(it.get("creation_date")),
                    engagement=it.get("view_count"),
                    query=query,
                )
            )
        return hits, self._call(f"{query} @ {site}", API, t0, hits)
