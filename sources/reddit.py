"""Reddit adapter: STUBBED. Self-serve API access is restricted, so this source is not used.
It is left as an interface for a contributor once access allows."""
from __future__ import annotations

import time

from .base import Source

STATUS = "STUBBED"


class Reddit(Source):
    name = "reddit"
    pain_capable = False

    def search(self, query: str, **kw):
        return [], self._call(query, "reddit://stubbed", time.time(), error="STUBBED: adapter not enabled")
