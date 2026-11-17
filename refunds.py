"""Refunds: always founder-approved (@gated("refund")); the system never refunds on its own.
A refund revokes the download token, so the download returns 403."""
from __future__ import annotations

import delivery
from proveit import approval, db
from proveit.gates import canonical_json
from proveit.log import utcnow


def payload_for(order_id: str) -> bytes:
    order = db.query_one("SELECT id, amount FROM orders WHERE id=?", (order_id,))
    if order is None:
        raise KeyError(order_id)
    return canonical_json({"action": "refund", "order_id": order["id"], "amount": order["amount"]}).encode()


def request(run_id: str, order_id: str):
    """Open a pending refund approval for the founder (UI order page or CLI). Asking twice for the same
    order returns the approval that is already waiting instead of opening another one."""
    payload = payload_for(order_id)
    for ap in approval.list_approvals(run_id, "pending"):
        if ap.action == "refund" and ap.note == f"refund {order_id}":
            return ap
    return approval.request(run_id, "refund", payload, note=f"refund {order_id}", content_type="application/json")


@approval.gated("refund")
def _execute(payload: bytes, order_id: str, run_id: str | None = None) -> dict:
    order = db.query_one("SELECT * FROM orders WHERE id=?", (order_id,))
    db.execute("INSERT OR IGNORE INTO refunds (order_id, approval_id, amount, created_at) VALUES (?,?,?,?)",
               (order_id, None, order["amount"], utcnow()))
    db.execute("UPDATE orders SET status='refunded' WHERE id=?", (order_id,))
    delivery.revoke(order_id)
    return {"order_id": order_id, "refunded": order["amount"], "test": True}


def refund(order_id: str, approval_id: str | None) -> dict:
    order = db.query_one("SELECT run_id FROM orders WHERE id=?", (order_id,))
    result = _execute(payload_for(order_id), approval_id, order_id, run_id=order["run_id"] if order else None)
    db.execute("UPDATE refunds SET approval_id=? WHERE order_id=?", (approval_id, order_id))
    return result
