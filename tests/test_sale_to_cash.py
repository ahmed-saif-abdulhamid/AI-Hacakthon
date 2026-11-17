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
