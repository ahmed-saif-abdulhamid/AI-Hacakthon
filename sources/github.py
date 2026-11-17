"""GitHub repository search: competitor / alternative evidence (optional free GITHUB_TOKEN)."""
from __future__ import annotations

import os
import time
from datetime import datetime

from .base import Source, get_json, make_hit


class GitHub(Source):
    name = "github"
    pain_capable = False
    api = "https://api.github.com/search/repositories"

    def search(self, query: str, timeout: float = 8.0, **kw):
        t0 = time.time()
        headers = {"Accept": "application/vnd.github+json"}
        if os.environ.get("GITHUB_TOKEN"):
            headers["Authorization"] = "Bearer " + os.environ["GITHUB_TOKEN"]
        try:
            data = get_json(self.api, params={"q": query, "sort": "stars", "per_page": 5},
                            headers=headers, timeout=timeout)
        except Exception as e:  # noqa: BLE001
            return [], self._call(query, self.api, t0, error=str(e)[:160])
        hits = []
        for it in data.get("items", []):
            desc = (it.get("description") or "")[:400]
            if not desc:
                continue
            pushed = it.get("pushed_at")
            published = datetime.fromisoformat(pushed.replace("Z", "+00:00")) if pushed else None
            name = it.get("full_name", "")
            hits.append(make_hit("github", it.get("html_url", ""), name + ": " + desc, title=name,
                                 published_at=published, engagement=it.get("stargazers_count"), query=query))
        return hits, self._call(query, self.api, t0, hits)
