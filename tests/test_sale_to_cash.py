"""MOCKED sale to cash: purchase, delivery, idempotent webhook, gated refund, reconciliation."""

from __future__ import annotations

import pytest

import delivery
import payments
import reconcile
import refunds
import webhooks
from proveit import approval


@pytest.fixture
def paid_order():
    p = payments.MockPaymentProvider()
    oid = p.create_order("r1", 39.0)
    event = p.create_checkout(oid, 39.0)
    first = webhooks.handle(event)
    return oid, event, first


def test_purchase_triggers_delivery(paid_order):
    oid, event, first = paid_order
    assert event["test"] is True and event["fee"] == payments.fee_for(39.0)
    assert first["delivered"] and delivery.check(first["token"]) == oid


def test_webhook_replay_gives_one_delivery(paid_order):
    oid, event, _ = paid_order
    replay = webhooks.handle(event)
    assert replay == {"status": 200, "duplicate": True, "delivered": False}
    assert delivery.delivery_count(oid) == 1


def test_refund_without_approval_raises(paid_order):
    oid, _, first = paid_order
    with pytest.raises(approval.ApprovalRequired):
        refunds.refund(oid, None)
    assert delivery.check(first["token"]) == oid


def test_refund_with_approval_revokes_download(paid_order):
    from fastapi.testclient import TestClient

    from app.api import app

    oid, _, first = paid_order
    ap = refunds.request("r1", oid)
    approval.auto_approve(ap.id)
    refunds.refund(oid, ap.id)
    with pytest.raises(delivery.AccessDenied):
        delivery.check(first["token"])
    assert TestClient(app).get(f"/download/{first['token']}").status_code == 403


def test_reconciliation_balances(paid_order):
    oid, _, _ = paid_order
    csv_text, summary = reconcile.run("r1")
    assert summary == {"orders": 1, "mismatches": 0, "balanced": True}
    assert "matched" in csv_text and oid in csv_text


def test_no_card_fields_anywhere():
    from pathlib import Path

    root = Path(__file__).resolve().parent.parent
    for f in list((root / "templates").glob("*.j2")) + [root / "app" / "ui.py"]:
        text = f.read_text(encoding="utf-8").lower()
        assert "cardnumber" not in text.replace(" ", "") and "cvv" not in text and 'type="card' not in text


def test_forged_or_altered_event_is_refused(paid_order):
    oid, event, _ = paid_order
    forged = dict(event, event_id="evt_forged", amount=0)  # signature no longer matches
    with pytest.raises(webhooks.BadEvent) as e:
        webhooks.handle(forged)
    assert e.value.status == 401
    with pytest.raises(webhooks.BadEvent):
        webhooks.handle({"event_id": "x"})  # malformed: 400, never a 500


def test_a_paid_order_is_never_paid_or_delivered_twice(paid_order):
    oid, event, _ = paid_order
    second = dict(event, event_id="evt_second_payment")
    second["signature"] = webhooks.sign(second)  # validly signed, but the order is already paid
    res = webhooks.handle(second)
    assert res["delivered"] is False and delivery.delivery_count(oid) == 1


def test_webhook_endpoint_returns_4xx_not_500():
    from fastapi.testclient import TestClient

    from app.api import app

    c = TestClient(app)
    assert c.post("/webhooks/mock", json={}).status_code == 400
    assert (
        c.post("/webhooks/mock", content=b"not json", headers={"content-type": "application/json"}).status_code == 400
    )


def test_customer_refund_request_runs_once_approved(paid_order):
    from proveit import orchestrator

    oid, _, first = paid_order
    ap = refunds.request("r1", oid)
    assert refunds.request("r1", oid).id == ap.id  # asking twice does not open a second approval
    with pytest.raises(approval.ApprovalRequired):
        refunds.refund(oid, None)
    approval.auto_approve(ap.id)
    orchestrator.on_approval_decided(ap.id)
    with pytest.raises(delivery.AccessDenied):
        delivery.check(first["token"])  # access revoked: the download now returns 403
