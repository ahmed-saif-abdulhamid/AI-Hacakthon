"""Per-source circuit breakers, so a sick public API fails fast instead of being called into.

Each source (``hn``, ``stackexchange``, ``github``, ``searxng``, ``wikipedia``) has one breaker:

* **closed**: calls go through. ``FAILURE_THRESHOLD`` consecutive failures open it.
* **open**: calls are refused at once with ``CircuitOpenError`` for ``COOLDOWN_SECONDS``.
* **half-open**: after the cooldown one trial call goes through; success closes the breaker,
  failure opens it for another cooldown. Other callers are refused while the trial is running.

Breakers are process-wide and thread-safe (the orchestrator queries sources in parallel).
"""

from __future__ import annotations

import threading
import time
from collections.abc import Callable
from enum import Enum

FAILURE_THRESHOLD = 3
COOLDOWN_SECONDS = 60.0


class CircuitOpenError(Exception):
    """Raised instead of calling a source whose breaker is open."""

    def __init__(self) -> None:
        super().__init__("circuit open")


class State(Enum):
    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"


class CircuitBreaker:
    def __init__(
        self,
        failure_threshold: int = FAILURE_THRESHOLD,
        cooldown_seconds: float = COOLDOWN_SECONDS,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._failure_threshold = failure_threshold
        self._cooldown_seconds = cooldown_seconds
        self._clock = clock
        self._lock = threading.Lock()
        self._state = State.CLOSED
        self._failures = 0
        self._opened_at = 0.0

    @property
    def state(self) -> State:
        with self._lock:
            return self._state

    def allow(self) -> bool:
        """True if a call may go out now. Moves an open breaker to half-open once the cooldown is over."""
        with self._lock:
            if self._state is State.CLOSED:
                return True
            if self._state is State.OPEN and self._clock() - self._opened_at >= self._cooldown_seconds:
                self._state = State.HALF_OPEN
                return True  # the single trial call
            return False

    def record_success(self) -> None:
        with self._lock:
            self._state = State.CLOSED
            self._failures = 0

    def record_failure(self) -> None:
        with self._lock:
            self._failures += 1
            if self._state is State.HALF_OPEN or self._failures >= self._failure_threshold:
                self._state = State.OPEN
                self._opened_at = self._clock()


_registry_lock = threading.Lock()
_breakers: dict[str, CircuitBreaker] = {}


def breaker(source: str) -> CircuitBreaker:
    """The shared breaker for ``source`` (created on first use)."""
    with _registry_lock:
        return _breakers.setdefault(source, CircuitBreaker())


def reset() -> None:
    """Forget every breaker's state (tests only)."""
    with _registry_lock:
        _breakers.clear()
