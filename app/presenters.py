"""Turn runs into the JSON views the console renders."""

from __future__ import annotations

import json
import re

from app.settings import DEMO, PROMOTED_RUNS_FILE
from proveit import db, decisions, gates, orchestrator
from proveit.orchestrator import Run

# What works and what is mocked, shown in the console and returned by the health check.
STATUS_TABLE = [
    ("Intake + eligibility check", "Working"),
    ("1.1 Find opportunities", "Working"),
    ("1.2 Evidence ledger", "Working"),
    ("1.3 Market definition", "Working"),
    ("1.4 Mom Test interview kit", "Working"),
    ("Gate 1: evidence", "Working"),
    ("2.1 Lean Canvas", "Working"),
    ("2.2 Landing page + waitlist", "Working"),
    ("Public hosting", "STUBBED"),
    ("Gate 2: demand", "Working"),
    ("3.1 Build MVP toolkit", "Working"),
    ("Gate 3: tests", "Working"),
    ("4.1 Pricing", "Working"),
    ("4.2 Policy drafts", "Working"),
    ("Gate 4", "Working"),
    ("5.1 Store page + launch post draft", "Working"),
    ("5.2 Payment -> delivery -> refund", "MOCKED"),
    ("5.3 Reconciliation", "MOCKED"),
    ("Posting to external platforms", "STUBBED"),
    ("6 Operate and learn", "STUBBED"),
    ("Reddit source", "STUBBED"),
]

MAX_TITLE_CHARS = 80
CALIBRATION_LABEL = "backtest"
_IDEA_PREFIX = re.compile(r"(?i)^idea\s*:\s*")
_ORDER_FIELDS = ("id", "amount")


def idea_text(run: Run) -> str:
    """The founder's idea as typed, without a leading "Idea:" label."""
    brief = run.state.get("brief") or {}
    raw = run.brief_raw or {}
    idea = brief.get("idea") or raw.get("fields", {}).get("idea") or raw.get("text", "")
    return _IDEA_PREFIX.sub("", str(idea).strip())


def run_title(run: Run) -> str | None:
    """The chosen variant's title, else the first line of the idea."""
    variants = run.state.get("variants") or []
    if variants:
        chosen = min(len(variants), run.state.get("variant_n", 1))
        return variants[chosen - 1].get("title")
    return idea_text(run).split("\n")[0][:MAX_TITLE_CHARS] or None


def title_for(run_id: str) -> str | None:
    try:
        run = orchestrator.load(run_id)
    except Exception:  # noqa: BLE001 - one damaged run must not break the run list
        return None
    return run_title(run)


def example_run_ids() -> set[str]:
    """The committed weak and strong example runs."""
    try:
        promoted = json.loads(PROMOTED_RUNS_FILE.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return set()
    return {promoted.get("weak"), promoted.get("strong")} - {None}


def run_summaries(runs: list[dict]) -> list[dict]:
    """Rows for the run list, each with a title and whether it is an example or a calibration run."""
    examples = example_run_ids()
    return [
        dict(
            row,
            title=title_for(row["id"]),
            example=row["id"] in examples,
            calibration=row.get("label") == CALIBRATION_LABEL,
        )
        for row in runs
    ]


def usage_from_log(run_id: str) -> dict:
    """Model usage summed from the persistent decision log (the in-memory counter resets on restart)."""
    calls = tokens_in = tokens_out = 0
    seconds = 0.0
    for row in db.query("SELECT model, extra FROM actions WHERE run_id=? AND model IS NOT NULL", (run_id,)):
        try:
            extra = json.loads(row.get("extra") or "{}")
        except ValueError:
            continue
        if "tokens_in" in extra:
            calls += 1
            tokens_in += int(extra.get("tokens_in") or 0)
            tokens_out += int(extra.get("tokens_out") or 0)
            seconds += float(extra.get("seconds") or 0)
    return {"calls": calls, "tokens_in": tokens_in, "tokens_out": tokens_out, "seconds": round(seconds, 1)}


def _current_claims(run: Run, research: dict) -> list[dict]:
    """Claims from the current variant's research, or every claim before research has run."""
    claims = run.state.get("claims", [])
    if not research:
        return claims
    hits = research.get("hits", {})
    return [c for c in claims if c.get("hit_id") in hits]


def _goalpost_moved(run: Run) -> bool:
    """True when the thresholds now differ from the ones pre-registered at the start of the run."""
    thresholds = run.state.get("thresholds")
    if not thresholds:
        return False
    return gates.thresholds_sha256(thresholds, run.brief_raw) != run.sha


def _latest_narration(run_id: str) -> str:
    rows = db.query(
        "SELECT text FROM telemetry WHERE run_id=? AND kind IN ('narration','progress') ORDER BY seq DESC LIMIT 1",
        (run_id,),
    )
    return rows[0]["text"] if rows else ""


def run_view(run: Run, *, working: bool) -> dict:
    """Everything the console shows for one run."""
    state = run.state
    variant_n = state.get("variant_n", 1)
    research = state.get("research", {}).get(str(variant_n), {})
    row = db.query_one("SELECT status, created_at FROM runs WHERE id=?", (run.id,)) or {}
    order = state.get("order")
    return {
        "run_id": run.id,
        "label": run.label,
        "mode": run.mode,
        "stage": run.stage,
        "phase": state.get("phase", 1),
        "idea": idea_text(run),
        "title": run_title(run),
        "brief": state.get("brief"),
        "thresholds_sha256": run.sha,
        "goalpost_moved": _goalpost_moved(run),
        "thresholds": state.get("thresholds", {}).get("gate1_evidence"),
        "variants": state.get("variants", []),
        "variant_n": variant_n,
        "claims": _current_claims(run, research),
        "metrics": research.get("metrics"),
        "coverage_rows": research.get("coverage_rows"),
        "gate1": state.get("gate1"),
        "gate2": state.get("gate2"),
        "gate3": state.get("gate3"),
        "gate4": state.get("gate4"),
        "debate": state.get("debate"),
        "override": state.get("override"),
        "clarify": state.get("clarify"),
        "pending_approval": state.get("pending_approval"),
        "usage": usage_from_log(run.id),
        "error": state.get("error"),
        "error_message": state.get("error_message"),
        "order": {k: order.get(k) for k in _ORDER_FIELDS} if order else None,
        "files": sorted(p.name for p in run.dir.iterdir() if p.is_file()),
        "working": working,
        "actions": [] if DEMO else decisions.allowed_decisions(run),
        "status": row.get("status"),
        "latest": _latest_narration(run.id),
        "created_at": row.get("created_at"),
    }
