"""Approvals: the founder sees the exact payload and approves or rejects it by its SHA-256."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException
from fastapi.responses import PlainTextResponse
from pydantic import BaseModel, Field

from app.background import run_workers
from proveit import approval, decisions, metrics
from proveit.models import Approval

router = APIRouter(prefix="/approvals", tags=["approvals"])

SHA256_HEX_LENGTH = 64
PAYLOAD_HASH_HEADER = "X-Payload-SHA256"


class ApproveIn(BaseModel):
    approve: bool
    payload_sha256: str = Field(max_length=SHA256_HEX_LENGTH)


def _load(approval_id: str) -> Approval:
    found = approval.load(approval_id)
    if found is None:
        raise HTTPException(404)
    return found


@router.get("")
def list_approvals(run: str | None = None, status: str | None = None) -> list[dict]:
    return [a.model_dump(mode="json") for a in approval.list_approvals(run, status)]


@router.get("/{approval_id}/payload")
def approval_payload(approval_id: str) -> PlainTextResponse:
    pending = _load(approval_id)
    payload, _content_type = approval.blob(pending.payload_sha256)
    return PlainTextResponse(payload.decode("utf-8", "replace"), headers={PAYLOAD_HASH_HEADER: pending.payload_sha256})


@router.post("/{approval_id}")
def decide_approval(approval_id: str, body: ApproveIn) -> dict:
    """Approve or reject, only if the payload the founder saw is the one still awaiting approval."""
    pending = _load(approval_id)
    if pending.status != "pending":
        raise HTTPException(409, "this approval was already decided")
    if body.payload_sha256 != pending.payload_sha256:
        raise HTTPException(409, "the payload you saw does not match the payload awaiting approval")
    decided = approval.decide(approval_id, body.approve, via="ui")
    metrics.increment("approval_decided", action=decided.action, outcome=decided.status)
    decisions.on_approval_decided(approval_id)
    run_workers.advance(decided.run_id)
    return decided.model_dump(mode="json")
