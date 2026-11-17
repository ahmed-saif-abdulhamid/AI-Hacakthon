"""A run: one founder idea moving through the six phases, persisted in the ``runs`` table.

``Run`` holds the row plus its JSON state and its output folder (``runs/<run_id>/``). Stages read
and mutate ``run.state`` and call ``run.save(stage)`` to move the run on; nothing else writes runs.
"""

from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime
from enum import StrEnum
from functools import lru_cache
from pathlib import Path

import yaml

from .. import db, voice
from ..log import emit, log_action, utcnow
from ..models import Claim, FounderBrief, Variant
from ..startup import runs_dir

ROOT = Path(__file__).resolve().parent.parent.parent
RUNTIME_CONFIG = ROOT / "config" / "runtime.yaml"

PHASE_NAMES = {
    1: "Discover",
    2: "Validate",
    3: "Build",
    4: "Commercial setup",
    5: "Launch (sell, deliver, get paid)",
    6: "Operate and learn",
}


class Stage(StrEnum):
    """Where a run is. Values are stored in the database, so they never change."""

    INTAKE = "intake"
    PHASE1 = "phase1"
    PHASE2 = "phase2"
    GATE2 = "gate2"
    PHASE3 = "phase3"
    PHASE4 = "phase4"
    PHASE5 = "phase5"
    PAYMENT_TEST = "payment_test"
    REFUND = "refund"
    PHASE6 = "phase6"
    AWAIT_APPROVAL = "await_approval"
    AWAIT_OVERRIDE = "await_override"
    AWAIT_GATE4 = "await_gate4"
    AWAIT_CLARIFY = "await_clarify"
    AWAIT_FOUNDER = "await_founder"
    STOPPED = "stopped"
    DONE = "done"


class Status(StrEnum):
    RUNNING = "running"
    WAITING = "waiting"
    STOPPED = "stopped"
    ERROR = "error"
    DONE = "done"


WAITING = frozenset(
    {Stage.AWAIT_APPROVAL, Stage.AWAIT_OVERRIDE, Stage.AWAIT_GATE4, Stage.AWAIT_CLARIFY, Stage.AWAIT_FOUNDER}
)
FINISHED = frozenset({Stage.DONE, Stage.STOPPED})


@lru_cache(maxsize=1)
def runtime() -> dict:
    """Research caps and limits per mode (``config/runtime.yaml``). Mode never changes a gate's answer."""
    return yaml.safe_load(RUNTIME_CONFIG.read_text(encoding="utf-8"))


class Run:
    def __init__(self, row: dict):
        self.id: str = row["id"]
        self.label: str | None = row.get("label")
        self.mode: str = row.get("mode") or "live"
        self.stage: str | None = row.get("stage")
        self.status: str | None = row.get("status")
        self.created_at: str | None = row.get("created_at")
        self.brief_raw: dict = json.loads(row.get("brief_json") or "{}")
        self.state: dict = json.loads(row.get("state_json") or "{}")
        self.sha: str = row.get("thresholds_sha256") or ""
        self.dir: Path = runs_dir() / self.id
        self.dir.mkdir(parents=True, exist_ok=True)

    # ---- persistence -------------------------------------------------------------

    def save(self, stage: str | None = None, outcome: str | None = None, status: str | None = None) -> None:
        if stage:
            self.stage = stage
        if status:
            self.status = status
        db.execute(
            "UPDATE runs SET stage=?, state_json=?, outcome=COALESCE(?, outcome), status=COALESCE(?, status)"
            " WHERE id=?",
            (self.stage, json.dumps(self.state, default=str), outcome, status, self.id),
        )

    def write(self, name: str, text: str) -> Path:
        """Write one output file into the run's folder and tell the console about it."""
        path = self.dir / name
        path.write_text(text, encoding="utf-8", newline="\n")
        emit(self.id, self.phase, "file", name, path=str(path))
        return path

    def read(self, name: str) -> str:
        """An output file written earlier in this run, or "" if it was never written."""
        path = self.dir / name
        return path.read_text(encoding="utf-8") if path.exists() else ""

    # ---- narration -------------------------------------------------------------------

    @property
    def phase(self) -> int:
        return self.state.get("phase", 1)

    def say(self, kind: str, **fields) -> None:
        """A spoken narration line for the console (text from ``voice.line``)."""
        text = voice.line(kind, **fields)
        emit(self.id, self.phase, "narration", text, event=kind)
        voice.prerender(text)

    def progress(self, phase: int, text: str, **data) -> None:
        self.state["phase"] = phase
        emit(self.id, phase, "progress", text, **data)

    # ---- typed views of the state ----------------------------------------------------

    @property
    def brief(self) -> FounderBrief:
        return FounderBrief(**self.state["brief"])

    @property
    def thresholds(self) -> dict:
        return self.state["thresholds"]

    def claims(self) -> list[Claim]:
        return [Claim(**c) for c in self.state.get("claims", [])]

    def ledger(self) -> dict[str, Claim]:
        return {c.id: c for c in self.claims()}

    def variant(self, n: int | None = None) -> Variant:
        n = n or self.state.get("variant_n", 1)
        return Variant(**self.state["variants"][n - 1])

    def variant_claims(self, n: int | None = None) -> list[Claim]:
        """The claims found while researching one variant (the current one by default)."""
        n = n or self.state.get("variant_n", 1)
        hits = self.state.get("research", {}).get(str(n), {}).get("hits", {})
        return [c for c in self.claims() if c.hit_id in hits]

    def next_variant(self) -> int | None:
        """The best-scored angle not researched yet (the pivot target), or None."""
        tried = set(self.state.get("research", {})) | {str(self.state.get("variant_n", 1))}
        ranking = self.state.get("ranking") or []
        excluded = {r["n"] for r in ranking if r.get("excluded")}
        order = [r["n"] for r in sorted(ranking, key=lambda r: -r.get("signal", 0)) if r["n"] not in excluded]
        order += [
            i for i in range(1, len(self.state.get("variants") or []) + 1) if i not in order and i not in excluded
        ]
        return next((n for n in order if str(n) not in tried), None)


def new_run_id() -> str:
    return datetime.now(UTC).strftime("r%Y%m%d-%H%M%S-") + uuid.uuid4().hex[:4]


def create(brief_raw: dict, mode: str, label: str | None, thresholds: dict, sha: str) -> Run:
    """Insert a new run at the intake stage and return it."""
    run_id = new_run_id()
    db.execute(
        "INSERT INTO runs (id, created_at, label, mode, brief_json, stage, status, thresholds_sha256, state_json)"
        " VALUES (?,?,?,?,?,?,?,?,?)",
        (
            run_id,
            utcnow(),
            label,
            mode,
            json.dumps(brief_raw),
            Stage.INTAKE,
            Status.RUNNING,
            sha,
            json.dumps({"thresholds": thresholds, "phase": 1}),
        ),
    )
    return load(run_id)


def load(run_id: str) -> Run:
    row = db.query_one("SELECT * FROM runs WHERE id=?", (run_id,))
    if row is None:
        raise KeyError(run_id)
    return Run(row)


def list_runs(limit: int = 30) -> list[dict]:
    return db.query(
        "SELECT id, created_at, label, mode, stage, status, outcome FROM runs ORDER BY created_at DESC LIMIT ?",
        (limit,),
    )


def log_gate(run: Run, action: str, dec, **extra) -> None:
    """The decision-log entry every gate writes: code decides, so model is None and cost is 0."""
    log_action(
        run.id,
        "gatekeeper",
        action,
        model=None,
        cost=0,
        outcome=dec.outcome,
        reason=dec.reason,
        rule_fired=dec.rule_fired,
        **extra,
    )
