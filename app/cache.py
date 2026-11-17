"""A small thread-safe, size-bounded map whose entries expire after a fixed time."""

from __future__ import annotations

import threading
import time
from collections import OrderedDict
from collections.abc import Callable
from typing import Generic, TypeVar

V = TypeVar("V")


class TtlCache(Generic[V]):
    """Entries live for ``ttl_s`` seconds; beyond ``max_entries`` the oldest are dropped first."""

    def __init__(self, ttl_s: float, max_entries: int, clock: Callable[[], float] = time.monotonic):
        self._ttl_s = ttl_s
        self._max_entries = max_entries
        self._clock = clock
        self._entries: OrderedDict[str, tuple[float, V]] = OrderedDict()
        self._lock = threading.Lock()

    def get(self, key: str) -> V | None:
        with self._lock:
            self._expire()
            entry = self._entries.get(key)
            return entry[1] if entry else None

    def put(self, key: str, value: V) -> None:
        with self._lock:
            self._expire()
            self._entries.pop(key, None)
            self._insert(key, value)

    def add(self, key: str, value: V) -> bool:
        """Store ``value`` only if ``key`` has no live entry; return whether it was stored."""
        with self._lock:
            self._expire()
            if key in self._entries:
                return False
            self._insert(key, value)
            return True

    def _insert(self, key: str, value: V) -> None:
        self._entries[key] = (self._clock(), value)
        while len(self._entries) > self._max_entries:
            self._entries.popitem(last=False)

    def _expire(self) -> None:
        cutoff = self._clock() - self._ttl_s
        while self._entries:
            oldest_key, (stored_at, _) = next(iter(self._entries.items()))
            if stored_at > cutoff:
                break
            del self._entries[oldest_key]
