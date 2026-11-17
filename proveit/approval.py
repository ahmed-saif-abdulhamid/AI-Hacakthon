"""Founder approval, enforced in code and bound to the exact payload bytes.

* ``request`` stores the payload as a blob keyed by its SHA-256 and opens a pending row.
* ``decide`` is called only by the UI approve/reject buttons or the CLI.
* ``@gated(action)`` refuses to run unless an approved row exists whose action and
  ``payload_sha256`` match the bytes being executed. One changed byte voids it.
* ``spend``, ``sign`` and ``create_account`` always raise ``NotEnabled``.
"""

from __future__ import annotations

import functools
import hashlib
import os
import uuid
from collections.abc import Callable
from typing import TypeVar, get_args

from . import db
from .log import log_action, utcnow
from .models import Approval, GatedAction

GATED_ACTIONS: tuple[str, ...] = get_args(GatedAction)
NEVER_ENABLED = ("spend", "sign", "create_account")
APPROVAL_ID_HEX_CHARS = 10

R = TypeVar("R")


class ApprovalRequired(Exception):
    """Raised when a gated action runs without a matching founder approval."""


class NotEnabled(Exception):
    """Raised by actions this system never performs (spend, sign, create accounts)."""


def sha256(payload: bytes) -> str:
    """Hex SHA-256 of the payload: the identity an approval is bound to."""
    return hashlib.sha256(payload).hexdigest()


def _row(r: dict | None) -> Approval | None:
    return Approval(**r) if r else None


def request(run_id: str, action: str, payload: bytes, note: str = "", content_type: str = "text/plain") -> Approval:
    """Store ``payload`` and open a pending approval bound to its SHA-256."""
    if action not in GATED_ACTIONS:
        raise ValueError(f"unknown gated action {action}")
    digest = sha256(payload)
    db.execute(
        "INSERT OR IGNORE INTO blobs (sha256, payload, content_type) VALUES (?,?,?)", (digest, payload, content_type)
    )
    ap = Approval(
        id="AP-" + uuid.uuid4().hex[:APPROVAL_ID_HEX_CHARS],
        run_id=run_id,
        action=action,
        payload_sha256=digest,
        status="pending",
        note=note,
    )
    db.execute(
        "INSERT INTO approvals (id, run_id, action, payload_sha256, status, decided_by,"
        " decided_at, created_at, note) VALUES (?,?,?,?,?,?,?,?,?)",
        (ap.id, run_id, action, digest, "pending", None, None, utcnow(), note),
    )
    log_action(
        run_id, "approval", f"request_approval_{action}", approved_by=None, approval_id=ap.id, payload_sha256=digest
    )
    return ap


def load(approval_id: str) -> Approval | None:
    """The approval with this id, or None."""
    return _row(db.query_one("SELECT * FROM approvals WHERE id = ?", (approval_id,)))


def list_approvals(run_id: str | None = None, status: str | None = None) -> list[Approval]:
    """Approvals, optionally filtered by run and by status."""
    sql, params = "SELECT * FROM approvals WHERE 1=1", []
    if run_id:
        sql += " AND run_id = ?"
        params.append(run_id)
    if status:
        sql += " AND status = ?"
        params.append(status)
    return [Approval(**r) for r in db.query(sql + " ORDER BY created_at", tuple(params))]


def decide(approval_id: str, approve: bool, via: str = "cli") -> Approval:
    """Record the founder's decision. Called only from the UI buttons or the CLI."""
    ap = load(approval_id)
    if ap is None:
        raise KeyError(approval_id)
    if ap.status != "pending":
        return ap
    status = "approved" if approve else "rejected"
    db.execute(
        "UPDATE approvals SET status=?, decided_by=?, decided_at=? WHERE id=?",
        (status, "founder", utcnow(), approval_id),
    )
    log_action(
        ap.run_id,
        "founder",
        f"{'approve' if approve else 'reject'}_{ap.action}",
        approved_by="founder" if approve else None,
        approval_id=approval_id,
        payload_sha256=ap.payload_sha256,
        via=via,
    )
    return load(approval_id)


def auto_approve(approval_id: str) -> Approval:
    """Test helper. Refuses to run outside PROVEIT_ENV=test."""
    if os.environ.get("PROVEIT_ENV") != "test":
        raise RuntimeError("auto_approve is only available when PROVEIT_ENV=test")
    return decide(approval_id, True, via="test")


def blob(digest: str) -> tuple[bytes, str] | None:
    """The stored payload bytes and content type for a SHA-256, or None."""
    r = db.query_one("SELECT payload, content_type FROM blobs WHERE sha256 = ?", (digest,))
    return (bytes(r["payload"]), r["content_type"]) if r else None


def _matches(ap: Approval | None, action: str, payload: bytes) -> bool:
    """True only for an approved row for this action whose hash matches these exact bytes."""
    return bool(ap and ap.status == "approved" and ap.action == action and ap.payload_sha256 == sha256(payload))


def gated(action: str) -> Callable[[Callable[..., R]], Callable[..., R]]:
    """Decorate an executor ``fn(payload, *args)``; the wrapper takes ``(payload, approval_id, *args)``
    and runs ``fn`` only with a matching founder approval (see the module docstring)."""
    if action not in GATED_ACTIONS:
        raise ValueError(action)

    def deco(fn: Callable[..., R]) -> Callable[..., R]:
        @functools.wraps(fn)
        def inner(payload: bytes, approval_id: str | None, *a: object, **k: object) -> R:
            ap = load(approval_id) if approval_id else None
            run_id = ap.run_id if ap else k.get("run_id")
            if not _matches(ap, action, payload):
                log_action(
                    run_id,
                    "executor",
                    f"blocked_{action}",
                    approved_by=None,
                    approval_id=approval_id,
                    reason="no matching founder approval for these exact bytes",
                )
                raise ApprovalRequired(action)
            if action in NEVER_ENABLED:
                log_action(run_id, "executor", f"not_enabled_{action}", approved_by=None, approval_id=approval_id)
                raise NotEnabled(f"{action} is never performed by this system")
            log_action(
                run_id,
                "executor",
                action,
                approved_by="founder",
                approval_id=approval_id,
                payload_sha256=ap.payload_sha256,
            )
            return fn(payload, *a, **k)

        return inner

    return deco


# ---- gated executors -------------------------------------------------------


def _publish(kind: str, payload: bytes, run_id: str) -> str:
    digest = sha256(payload)
    db.execute(
        "INSERT OR REPLACE INTO published (run_id, kind, sha256, published_at) VALUES (?,?,?,?)",
        (run_id, kind, digest, utcnow()),
    )
    return digest


@gated("publish_landing_page")
def publish_landing_page(payload: bytes, run_id: str) -> str:
    """Serve the approved bytes at /p/<run_id> on localhost. Public hosting is STUBBED."""
    return _publish("landing", payload, run_id)


@gated("open_store")
def open_store(payload: bytes, run_id: str) -> str:
    """Serve the approved store page at /store/<run_id> on localhost."""
    return _publish("store", payload, run_id)


@gated("publish_post")
def publish_post(payload: bytes, run_id: str) -> str:
    """STUBBED: this system never posts; always raises NotEnabled."""
    raise NotEnabled("publish_post adapter is STUBBED: drafts are never posted by this system")


@gated("send_email")
def send_email(payload: bytes, run_id: str) -> str:
    """STUBBED: this system never sends anything; always raises NotEnabled."""
    raise NotEnabled("send_email adapter is STUBBED: nothing is ever sent by this system")


@gated("spend")
def spend(payload: bytes, run_id: str) -> None:  # pragma: no cover - always raises in the decorator
    """Spending money is never enabled; always raises NotEnabled."""
    raise NotEnabled("spend")


@gated("sign")
def sign(payload: bytes, run_id: str) -> None:  # pragma: no cover
    """Signing anything is never enabled; always raises NotEnabled."""
    raise NotEnabled("sign")


@gated("create_account")
def create_account(payload: bytes, run_id: str) -> None:  # pragma: no cover
    """Creating accounts is never enabled; always raises NotEnabled."""
    raise NotEnabled("create_account")


def published_payload(run_id: str, kind: str) -> tuple[bytes, str] | None:
    """The approved bytes and content type published for a run's page (landing or store), or None."""
    r = db.query_one("SELECT sha256 FROM published WHERE run_id=? AND kind=?", (run_id, kind))
    return blob(r["sha256"]) if r else None
