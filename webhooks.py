"""Webhook handler with an idempotency table keyed by event_id.
A replayed event returns 200 and causes no second delivery."""
from __future__ import annotations

import json

import delivery
from proveit import db
from proveit.log import log_action, utcnow


def handle(event: dict) -> dict:
    existing = db.query_one("SELECT event_id FROM webhook_events WHERE event_id=?", (event["event_id"],))
    order = db.query_one("SELECT run_id FROM orders WHERE id=?", (event.get("order_id"),))
    run_id = order["run_id"] if order else None
    if existing:
        log_action(run_id, "webhooks", "webhook_replay_ignored", event_id=event["event_id"], test=True)
        return {"status": 200, "duplicate": True, "delivered": False}
    db.execute("INSERT INTO webhook_events (event_id, type, received_at, payload) VALUES (?,?,?,?)",
               (event["event_id"], event["type"], utcnow(), json.dumps(event)))
    if event["type"] != "payment.succeeded":
        return {"status": 200, "duplicate": False, "delivered": False}
    db.execute("INSERT INTO payments (event_id, order_id, amount, fee, net, payout_id, created_at, test)"
               " VALUES (?,?,?,?,?,?,?,1)", (event["event_id"], event["order_id"], event["amount"], event["fee"],
                                            event["net"], event["payout_id"], utcnow()))
    db.execute("INSERT OR IGNORE INTO payouts (id, amount, created_at, test) VALUES (?,?,?,1)",
               (event["payout_id"], event["net"], utcnow()))
    db.execute("UPDATE orders SET status='paid' WHERE id=?", (event["order_id"],))
    log_action(run_id, "webhooks", "webhook_payment_succeeded", event_id=event["event_id"],
               order_id=event["order_id"], test=True)
    token = delivery.grant(event["order_id"])
    return {"status": 200, "duplicate": False, "delivered": True, "token": token}
