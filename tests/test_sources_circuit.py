"""Circuit breaker for the public evidence sources: a failing API is skipped fast, then retried."""

from __future__ import annotations

import httpx
import pytest

from proveit import metrics
from sources import circuit
from sources.circuit import CircuitBreaker, State
from sources.hn import HackerNews


class Clock:
    def __init__(self) -> None:
        self.now = 0.0

    def __call__(self) -> float:
        return self.now


@pytest.fixture(autouse=True)
def fresh_breakers():
    circuit.reset()
    metrics.reset()
    yield
    circuit.reset()
    metrics.reset()


def test_breaker_opens_after_consecutive_failures_and_half_opens_after_cooldown():
    clock = Clock()
    b = CircuitBreaker(failure_threshold=2, cooldown_seconds=30, clock=clock)
    b.record_failure()
    assert b.allow() and b.state is State.CLOSED
    b.record_failure()
    assert b.state is State.OPEN and not b.allow()

    clock.now = 30
    assert b.allow() and b.state is State.HALF_OPEN
    assert not b.allow(), "only one trial call while half-open"
    b.record_failure()
    assert b.state is State.OPEN and not b.allow()

    clock.now = 60
    assert b.allow()
    b.record_success()
    assert b.state is State.CLOSED and b.allow()


def test_a_success_resets_the_failure_count():
    b = CircuitBreaker(failure_threshold=2)
    b.record_failure()
    b.record_success()
    b.record_failure()
    assert b.state is State.CLOSED


def test_open_circuit_fails_fast_with_a_clear_error(monkeypatch):
    calls = []

    def failing_get(url, **kw):
        calls.append(url)
        raise httpx.ConnectTimeout("timed out")

    monkeypatch.setattr(httpx, "get", failing_get)
    hn = HackerNews()
    for n in range(circuit.FAILURE_THRESHOLD):
        hits, call = hn.search(f"circuit breaker test query {n}")
        assert hits == [] and not call.ok and "timed out" in call.error

    hits, call = hn.search("circuit breaker test query open")
    assert hits == [] and not call.ok and call.error == "circuit open"
    assert len(calls) == circuit.FAILURE_THRESHOLD, "no request once the circuit is open"
    assert metrics.value("source_call_failed", source="hn") == circuit.FAILURE_THRESHOLD
    assert metrics.value("source_circuit_open", source="hn") == 1
