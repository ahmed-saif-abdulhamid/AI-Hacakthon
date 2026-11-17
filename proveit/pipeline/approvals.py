"""Pausing a run for the founder: a gated action waits for approval of its exact bytes."""

from __future__ import annotations

from .. import approval
from ..log import emit
from .run import Run, Stage, Status


def wait_for_approval(run: Run, ap) -> None:
    """Record the pending approval on the run, tell the console, and stop until the founder decides."""
    run.state["pending_approval"] = {"id": ap.id, "action": ap.action, "sha": ap.payload_sha256}
    run.say("approval_needed", action=ap.action, sha=ap.payload_sha256)
    emit(run.id, run.phase, "approval", ap.action, approval_id=ap.id, sha=ap.payload_sha256)
    run.save(Stage.AWAIT_APPROVAL, status=Status.WAITING)


def request_approval(run: Run, action: str, payload: bytes, content_type: str, note: str) -> None:
    wait_for_approval(run, approval.request(run.id, action, payload, note=note, content_type=content_type))
