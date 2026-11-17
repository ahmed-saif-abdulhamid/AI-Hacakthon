"""MOCKED payment provider. Pure in-process mock: no real or sandbox payments, no card
fields, no keys. Every order and payment is flagged test=true and excluded from every gate.

Fee model: illustrative ASSUMPTION: 2.9% + $0.30, typical card-processor pricing.
"""

from __future__ import annotations

import uuid

from proveit import db
from proveit.log import log_action, utcnow

STATUS = "MOCKED"
FEE_NOTE = "illustrative ASSUMPTION: 2.9% + $0.30, typical card-processor pricing"
FEE_RATE, FEE_FIXED = 0.029, 0.30


def fee_for(amount: float) -> float:
    return round(amount * FEE_RATE + FEE_FIXED, 2)


class MockPaymentProvider:
    """create_checkout() simulates a successful test purchase and returns the webhook event."""

    name = "mock (MOCKED)"

    def create_order(self, run_id: str, amount: float) -> str:
        order_id = "ORD-" + uuid.uuid4().hex[:8]
        db.execute(
            "INSERT INTO orders (id, run_id, amount, status, created_at, test) VALUES (?,?,?,?,?,1)",
            (order_id, run_id, amount, "created", utcnow()),
        )
        log_action(run_id, "payments", "mock_create_order", order_id=order_id, amount=amount, test=True)
        return order_id

    def create_checkout(self, order_id: str, amount: float) -> dict:
        order = db.query_one("SELECT * FROM orders WHERE id=?", (order_id,))
        if order is None:
            raise KeyError(order_id)
        fee = fee_for(amount)
        event = {
            "event_id": "evt_" + uuid.uuid4().hex[:12],
            "type": "payment.succeeded",
            "order_id": order_id,
            "amount": amount,
            "fee": fee,
            "net": round(amount - fee, 2),
            "payout_id": "po_" + uuid.uuid4().hex[:8],
            "test": True,
        }
        import webhooks

        event["signature"] = webhooks.sign(event)  # the webhook refuses unsigned or altered events
        log_action(
            order["run_id"],
            "payments",
            "mock_checkout_succeeded",
            order_id=order_id,
            event_id=event["event_id"],
            amount=amount,
            fee=fee,
            test=True,
        )
        return event
