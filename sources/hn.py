"""Hacker News via the free Algolia API (no key). Stories and comments are HTML -> normalize()."""
from __future__ import annotations

import time

from .base import Source, get_json, make_hit, ts_to_dt

API = "https://hn.algolia.com/api/v1/search"


class HackerNews(Source):
    name = "hn"
    pain_capable = True

    def search(self, query: str, since_ts: int = 0, per_page: int = 20, timeout: float = 8.0,
               tags: str = "(story,comment)", **kw):
        """Pain queries search comments only: people describe their problems in replies, while stories are
        mostly product launches (which are competitor evidence, found via GitHub and story search)."""
        t0 = time.time()
        # optionalWords: rank records matching the most words first (Algolia otherwise needs all words).
        params = {"query": query, "tags": tags, "hitsPerPage": per_page, "optionalWords": query}
        if since_ts:
            params["numericFilters"] = f"created_at_i>{since_ts}"
        try:
            data = get_json(API, params=params, timeout=timeout)
        except Exception as e:  # noqa: BLE001
            return [], self._call(query, API, t0, error=str(e)[:160])
        hits = []
        for h in data.get("hits", []):
            text = h.get("comment_text") or h.get("story_text") or ""
            title = h.get("title") or h.get("story_title") or ""
            if not text and title:
                text = title
            if not text:
                continue
            hits.append(make_hit("hn", f"https://news.ycombinator.com/item?id={h['objectID']}", text,
                                 title=title, published_at=ts_to_dt(h.get("created_at_i")),
                                 engagement=h.get("points") or h.get("num_comments"), query=query))
        return hits, self._call(query, API, t0, hits)
