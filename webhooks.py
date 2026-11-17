"""Webhook handler (MOCKED provider) with three protections against double or forged delivery:

1. Signature: every mock event is HMAC-SHA256 signed with SECRET_KEY by payments.py; an unsigned or
   tampered event is refused (no row is written).
2. Idempotency by event: a replayed event_id returns 200 and causes no second delivery.
3. Idempotency by order: an order can be paid once. A second "payment.succeeded" for an order that is
   already paid or refunded is recorded as ignored, so a refund can never be undone by a late event.
"""

from __future__ import annotations

import hashlib
import hmac
import json

import delivery
from proveit import db
from proveit.log import log_action, utcnow

REQUIRED = ("event_id", "type", "order_id", "amount", "fee", "net", "payout_id")


class BadEvent(ValueError):
    """Maps to HTTP 400 (malformed) or 401 (bad signature)."""

    def __init__(self, message: str, status: int = 400):
        super().__init__(message)
        self.status = status


def _secret() -> bytes:
    from proveit.secrets_store import secret_key

    return secret_key().encode()


def sign(event: dict) -> str:
    body = json.dumps({k: v for k, v in event.items() if k != "signature"}, sort_keys=True, separators=(",", ":"))
    return hmac.new(_secret(), body.encode(), hashlib.sha256).hexdigest()


def handle(event: dict) -> dict:
    if not isinstance(event, dict) or any(k not in event for k in REQUIRED):
        raise BadEvent(
            "missing fields: " + ", ".join(k for k in REQUIRED if not isinstance(event, dict) or k not in event)
        )
    if not hmac.compare_digest(str(event.get("signature", "")), sign(event)):
        raise BadEvent("invalid signature", status=401)
    existing = db.query_one("SELECT event_id FROM webhook_events WHERE event_id=?", (event["event_id"],))
    order = db.query_one("SELECT run_id, status FROM orders WHERE id=?", (event.get("order_id"),))
    run_id = order["run_id"] if order else None
    if existing:
        log_action(run_id, "webhooks", "webhook_replay_ignored", event_id=event["event_id"], test=True)
        return {"status": 200, "duplicate": True, "delivered": False}
    if order is None:
        raise BadEvent("unknown order")
    db.execute(
        "INSERT INTO webhook_events (event_id, type, received_at, payload) VALUES (?,?,?,?)",
        (event["event_id"], event["type"], utcnow(), json.dumps(event)),
    )
    if event["type"] != "payment.succeeded":
        return {"status": 200, "duplicate": False, "delivered": False}
    if order["status"] != "created":
        log_action(
            run_id,
            "webhooks",
            "webhook_ignored_order_not_open",
            event_id=event["event_id"],
            order_id=event["order_id"],
            order_status=order["status"],
            test=True,
        )
        return {"status": 200, "duplicate": True, "delivered": False}
    db.execute(
        "INSERT INTO payments (event_id, order_id, amount, fee, net, payout_id, created_at, test)"
        " VALUES (?,?,?,?,?,?,?,1)",
        (
            event["event_id"],
            event["order_id"],
            event["amount"],
            event["fee"],
            event["net"],
            event["payout_id"],
            utcnow(),
        ),
    )
    db.execute(
        "INSERT OR IGNORE INTO payouts (id, amount, created_at, test) VALUES (?,?,?,1)",
        (event["payout_id"], event["net"], utcnow()),
    )
    db.execute("UPDATE orders SET status='paid' WHERE id=?", (event["order_id"],))
    log_action(
        run_id,
        "webhooks",
        "webhook_payment_succeeded",
        event_id=event["event_id"],
        order_id=event["order_id"],
        test=True,
    )
    token = delivery.grant(event["order_id"])
    return {"status": 200, "duplicate": False, "delivered": True, "token": token}
