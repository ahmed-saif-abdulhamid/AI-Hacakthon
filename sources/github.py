"""GitHub repository search: competitor / alternative evidence (optional free GITHUB_TOKEN)."""

from __future__ import annotations

import os
import time
from datetime import datetime

from proveit.models import Hit, SourceCall

from .base import DEFAULT_TIMEOUT_SECONDS, FETCH_ERRORS, Source, make_hit

API = "https://api.github.com/search/repositories"
RESULTS_PER_SEARCH = 5
MAX_DESCRIPTION_CHARS = 400


class GitHub(Source):
    name = "github"
    pain_capable = False

    def search(self, query: str, timeout: float = DEFAULT_TIMEOUT_SECONDS, **kw) -> tuple[list[Hit], SourceCall]:
        t0 = time.time()
        headers = {"Accept": "application/vnd.github+json"}
        if os.environ.get("GITHUB_TOKEN"):
            headers["Authorization"] = "Bearer " + os.environ["GITHUB_TOKEN"]
        params = {"q": query, "sort": "stars", "per_page": RESULTS_PER_SEARCH}
        try:
            data = self._get_json(API, params=params, headers=headers, timeout=timeout)
        except FETCH_ERRORS as e:
            return [], self._failed(query, API, t0, e)
        hits = [hit for it in data.get("items", []) if (hit := _repo_hit(it, query))]
        return hits, self._call(query, API, t0, hits)


def _repo_hit(item: dict, query: str) -> Hit | None:
    """A repository with a description, as competitor evidence; None for an undescribed repository."""
    desc = (item.get("description") or "")[:MAX_DESCRIPTION_CHARS]
    if not desc:
        return None
    pushed = item.get("pushed_at")
    name = item.get("full_name", "")
    return make_hit(
        "github",
        item.get("html_url", ""),
        name + ": " + desc,
        title=name,
        published_at=datetime.fromisoformat(pushed.replace("Z", "+00:00")) if pushed else None,
        engagement=item.get("stargazers_count"),
        query=query,
    )
