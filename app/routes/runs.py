"""Runs: start one, list them, read one's view, telemetry, log and files, retry, and founder decisions."""

from __future__ import annotations

import json
import re
from typing import Literal

from fastapi import APIRouter, HTTPException
from fastapi.responses import PlainTextResponse
from pydantic import BaseModel, Field

from app.background import run_workers
from app.cache import TtlCache
from app.presenters import run_summaries, run_view
from app.security import RUN_ID
from proveit import decisions, orchestrator
from proveit.log import entries, telemetry
from proveit.orchestrator import Run
from proveit.startup import runs_dir

router = APIRouter(prefix="/runs", tags=["runs"])

BRIEF_FIELDS = ("idea", "skills", "budget", "hours_per_week", "target_market", "values", "founder_name")
MAX_IDEA_CHARS = 2000
MAX_FIELD_CHARS = 300
RUN_LIST_LIMIT = 60
DUPLICATE_START_TTL_S = 15  # a second identical start within this window is a double click
MAX_TRACKED_STARTS = 256
_FILE_NAME = re.compile(r"[A-Za-z0-9_-][A-Za-z0-9_.-]*")

_recent_starts: TtlCache[str] = TtlCache(DUPLICATE_START_TTL_S, MAX_TRACKED_STARTS)


class RunIn(BaseModel):
    brief_text: str = Field("", max_length=8000)
    fields: dict = {}
    mode: str = "live"
    label: str | None = Field(None, max_length=40)


class DecideIn(BaseModel):
    decision: str = Field(max_length=40)
    reason: str = Field("", max_length=1000)


def _brief_fields(raw: dict) -> dict[str, str]:
    """The known, non-empty brief fields, each cut to its length limit."""
    return {
        key: str(value)[: MAX_IDEA_CHARS if key == "idea" else MAX_FIELD_CHARS]
        for key, value in raw.items()
        if key in BRIEF_FIELDS and value
    }


def _run_mode(requested: str) -> Literal["live", "full"]:
    return "full" if requested == "full" else "live"


def _load(run_id: str) -> Run:
    try:
        return orchestrator.load(run_id)
    except KeyError:
        raise HTTPException(404, "unknown run") from None


@router.post("")
def create_run(body: RunIn) -> dict:
    fields = _brief_fields(body.fields or {})
    if not (body.brief_text.strip() or fields.get("idea", "").strip()):
        raise HTTPException(422, "the idea is required")
    start_key = (body.brief_text.strip() + "|" + json.dumps(fields, sort_keys=True)).lower()
    previous = _recent_starts.get(start_key)
    if previous:
        return {"run_id": previous, "duplicate": True}
    run_id = orchestrator.start(body.brief_text, fields, _run_mode(body.mode), body.label)
    _recent_starts.put(start_key, run_id)
    run_workers.advance(run_id)
    return {"run_id": run_id}


@router.get("")
def list_runs() -> list[dict]:
    return run_summaries(orchestrator.list_runs(RUN_LIST_LIMIT))


@router.get("/{run_id}")
def get_run(run_id: str) -> dict:
    return run_view(_load(run_id), working=run_workers.is_working(run_id))


@router.get("/{run_id}/telemetry")
def get_telemetry(run_id: str, since: int = 0) -> list[dict]:
    return telemetry(run_id, since)


@router.get("/{run_id}/log")
def get_log(run_id: str) -> list[dict]:
    log = entries(run_id)
    for entry in log:
        entry.pop("_seq", None)
    return log


@router.get("/{run_id}/files/{name}")
def get_file(run_id: str, name: str) -> PlainTextResponse:
    if not RUN_ID.fullmatch(run_id) or not _FILE_NAME.fullmatch(name) or ".." in name:
        raise HTTPException(404, "no such file")
    base = (runs_dir() / run_id).resolve()
    path = (base / name).resolve()
    if base not in path.parents or not path.is_file():  # never serve anything outside the run's folder
        raise HTTPException(404, "no such file")
    return PlainTextResponse(path.read_text(encoding="utf-8"))


@router.post("/{run_id}/continue")
def continue_run(run_id: str) -> dict:
    """Try again after an error (the run keeps its stage, so it picks up where it stopped)."""
    try:
        result = orchestrator.retry(run_id)
    except KeyError:
        raise HTTPException(404, "unknown run") from None
    if result.get("ok"):
        run_workers.advance(run_id)
    return result


@router.post("/{run_id}/decide")
def decide(run_id: str, body: DecideIn) -> dict:
    try:
        result = decisions.founder_decide(run_id, body.decision, body.reason)
    except KeyError:
        raise HTTPException(404, "unknown run") from None
    if result.get("ok"):
        run_workers.advance(run_id)
    return result
