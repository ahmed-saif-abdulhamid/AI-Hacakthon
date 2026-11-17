"""In-process counters for alerting, exposed in the Prometheus text format.

The decision log records what happened for forensics; these counters are what an alert watches
(stage failures per minute, rejected webhooks, refunds), so a healthy server serving a broken
pipeline still pages someone. Counters reset when the process restarts, as Prometheus expects.
"""

from __future__ import annotations

import threading
from collections import Counter

_lock = threading.Lock()
_counts: Counter[tuple[str, tuple[tuple[str, str], ...]]] = Counter()


def increment(name: str, amount: int = 1, **labels: object) -> None:
    """Add ``amount`` to the counter ``name`` with the given labels (label values are stringified)."""
    key = (name, tuple(sorted((k, str(v)) for k, v in labels.items())))
    with _lock:
        _counts[key] += amount


def value(name: str, **labels: object) -> int:
    key = (name, tuple(sorted((k, str(v)) for k, v in labels.items())))
    with _lock:
        return _counts[key]


def render_prometheus() -> str:
    """Every counter as ``proveit_<name>_total{label="value"} <count>``, one per line."""
    with _lock:
        items = sorted(_counts.items())
    lines = []
    for (name, labels), count in items:
        label_text = ",".join(f'{k}="{_escape(v)}"' for k, v in labels)
        lines.append(f"proveit_{name}_total{{{label_text}}} {count}" if label_text else f"proveit_{name}_total {count}")
    return "\n".join(lines) + "\n"


def reset() -> None:
    """Clear every counter (tests only)."""
    with _lock:
        _counts.clear()


def _escape(value: str) -> str:
    return value.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n")
