"""Hacker News via the free Algolia API (no key). Stories and comments are HTML -> normalize()."""

from __future__ import annotations

import time

from proveit.models import Hit, SourceCall

from .base import DEFAULT_TIMEOUT_SECONDS, FETCH_ERRORS, Source, make_hit, ts_to_dt

API = "https://hn.algolia.com/api/v1/search"
DEFAULT_PER_PAGE = 20
MODERATED_MARKERS = ("[dead]", "[flagged]")


class HackerNews(Source):
    name = "hn"
    pain_capable = True

    def search(
        self,
        query: str,
        since_ts: int = 0,
        per_page: int = DEFAULT_PER_PAGE,
        timeout: float = DEFAULT_TIMEOUT_SECONDS,
        tags: str = "(story,comment)",
        **kw,
    ) -> tuple[list[Hit], SourceCall]:
        """Pain queries search comments only: people describe their problems in replies, while stories are
        mostly product launches (which are competitor evidence, found via GitHub and story search)."""
        t0 = time.time()
        # optionalWords: rank records matching the most words first (Algolia otherwise needs all words).
        params = {"query": query, "tags": tags, "hitsPerPage": per_page, "optionalWords": query}
        if since_ts:
            params["numericFilters"] = f"created_at_i>{since_ts}"
        try:
            data = self._get_json(API, params=params, timeout=timeout)
        except FETCH_ERRORS as e:
            return [], self._failed(query, API, t0, e)
        hits = [hit for record in data.get("hits", []) if (hit := _record_hit(record, query))]
        return hits, self._call(query, API, t0, hits)


def _record_hit(record: dict, query: str) -> Hit | None:
    """A story or comment as a hit; None when it has no text or was moderated away (not evidence)."""
    title = record.get("title") or record.get("story_title") or ""
    text = record.get("comment_text") or record.get("story_text") or title
    if not text:
        return None
    if title.strip().lower() in MODERATED_MARKERS or text.strip().lower().startswith(MODERATED_MARKERS):
        return None
    return make_hit(
        "hn",
        f"https://news.ycombinator.com/item?id={record['objectID']}",
        text,
        title=title,
        published_at=ts_to_dt(record.get("created_at_i")),
        engagement=record.get("points") or record.get("num_comments"),
        query=query,
    )
