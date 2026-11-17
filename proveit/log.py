"""Decision log: one SQLite row per agent action, exported to JSON per run.

Every entry carries the five required keys (action, sources, model, cost,
approved_by) plus timestamp, agent and run_id. Extra keys are stored as JSON.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime

from . import db

REQUIRED_KEYS = ("action", "sources", "model", "cost", "approved_by")


def utcnow() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def log_action(
    run_id: str | None,
    agent: str,
    action: str,
    sources: list[str] | None = None,
    model: str | None = None,
    cost: float = 0,
    approved_by: str | None = None,
    **extra,
) -> dict:
    if approved_by not in (None, "founder"):
        raise ValueError("approved_by must be 'founder' or None")
    entry = {
        "timestamp": utcnow(),
        "run_id": run_id,
        "agent": agent,
        "action": action,
        "sources": list(sources or []),
        "model": model,
        "cost": cost,
        "approved_by": approved_by,
    }
    clean_extra = {k: v for k, v in extra.items() if v is not None}
    db.execute(
        "INSERT INTO actions (run_id, timestamp, agent, action, sources, model, cost, approved_by, extra)"
        " VALUES (?,?,?,?,?,?,?,?,?)",
        (
            run_id,
            entry["timestamp"],
            agent,
            action,
            json.dumps(entry["sources"]),
            model,
            cost,
            approved_by,
            json.dumps(clean_extra, default=str),
        ),
    )
    entry.update(clean_extra)
    return entry


def emit(run_id: str, phase: int, kind: str, text: str, **data) -> None:
    """UI telemetry (progress, narration). Not part of the decision log."""
    db.execute(
        "INSERT INTO telemetry (run_id, ts, phase, kind, text, data) VALUES (?,?,?,?,?,?)",
        (run_id, utcnow(), phase, kind, text, json.dumps(data, default=str)),
    )


def telemetry(run_id: str, since_seq: int = 0) -> list[dict]:
    rows = db.query("SELECT * FROM telemetry WHERE run_id=? AND seq>? ORDER BY seq", (run_id, since_seq))
    for r in rows:
        r["data"] = json.loads(r["data"] or "{}")
    return rows


def _row_to_entry(r: dict) -> dict:
    entry = {
        "timestamp": r["timestamp"],
        "run_id": r["run_id"],
        "agent": r["agent"],
        "action": r["action"],
        "sources": json.loads(r["sources"] or "[]"),
        "model": r["model"],
        "cost": r["cost"] if r["cost"] is not None else 0,
        "approved_by": r["approved_by"],
    }
    if entry["cost"] == int(entry["cost"]):
        entry["cost"] = int(entry["cost"])
    entry.update(json.loads(r["extra"] or "{}"))
    return entry


def entries(run_id: str | None = None, since_seq: int = 0) -> list[dict]:
    if run_id is None:
        rows = db.query("SELECT * FROM actions WHERE seq > ? ORDER BY seq", (since_seq,))
    else:
        rows = db.query("SELECT * FROM actions WHERE run_id = ? AND seq > ? ORDER BY seq", (run_id, since_seq))
    out = []
    for r in rows:
        e = _row_to_entry(r)
        e["_seq"] = r["seq"]
        out.append(e)
    return out


def export(run_id: str) -> list[dict]:
    out = []
    for e in entries(run_id):
        e.pop("_seq", None)
        out.append(e)
    return out
