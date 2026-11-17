"""Phase 5, steps 2-3 (MOCKED): sale to cash, end to end.

A test purchase triggers a signed webhook, which delivers a download token; replaying the webhook
delivers nothing twice; a refund is refused without founder approval, then runs once approved, revokes
the download, and reconciliation matches orders, payments, fees and payouts.
"""

from __future__ import annotations

from ... import approval
from ...commerce import delivery, payments, reconcile, refunds, webhooks
from ...reports.launch import payment_test_log_md
from ..approvals import wait_for_approval
from ..run import Run, Stage, Status


def _can_download(token: str) -> bool:
    try:
        delivery.check(token)
    except delivery.AccessDenied:
        return False
    return True


def _refund_without_approval_is_blocked(order_id: str) -> bool:
    try:
        refunds.refund(order_id, None)
    except approval.ApprovalRequired:
        return True
    return False


def stage_payment_test(run: Run) -> None:
    """Purchase -> webhook -> delivery -> replay -> refund needs approval."""
    run.progress(5, "Sale to cash (MOCKED)")
    price = float(run.state["pricing"]["better"])
    provider = payments.MockPaymentProvider()
    order_id = provider.create_order(run.id, price)
    event = provider.create_checkout(order_id, price)
    first = webhooks.handle(event)
    replay = webhooks.handle(event)
    token = first.get("token")
    downloadable = _can_download(token)
    blocked = _refund_without_approval_is_blocked(order_id)
    steps = run.state.setdefault("payment_log", [])
    steps += [
        f"1. Simulated test purchase (MOCKED): order `{order_id}`, amount ${price:.2f}, test=true.",
        f"2. `payment.succeeded` event `{event['event_id']}`: fee ${event['fee']:.2f} ({payments.FEE_NOTE}), "
        f"net ${event['net']:.2f}, payout `{event['payout_id']}`.",
        f"3. Webhook handled: delivered={first['delivered']}; download token issued (24 h, HMAC-signed).",
        f"4. Webhook replay of the same event_id: status {replay['status']}, duplicate={replay['duplicate']}, "
        f"delivered={replay['delivered']}. Deliveries for this order: {delivery.delivery_count(order_id)}.",
        f"5. Download before refund: {'200 OK' if downloadable else 'denied'}.",
        f"6. Refund attempted without founder approval: {'blocked (ApprovalRequired)' if blocked else 'NOT BLOCKED'}.",
    ]
    run.say("payment")
    run.state["order"] = {"id": order_id, "token": token, "amount": price}
    ap = refunds.request(run.id, order_id)
    steps.append(f"7. Refund approval requested: `{ap.id}`, payload SHA-256 `{ap.payload_sha256}`.")
    wait_for_approval(run, ap)


def stage_refund(run: Run) -> None:
    """The founder approved the refund: execute it, prove the download is revoked, reconcile."""
    order = run.state["order"]
    result = refunds.refund(order["id"], run.state["refund_approval"])
    after = "200 OK (NOT REVOKED)" if _can_download(order["token"]) else "403 Forbidden (access revoked)"
    csv_text, summary = reconcile.run(run.id)
    run.write("phase5_step3_reconciliation.csv", csv_text)
    steps = run.state["payment_log"]
    steps += [
        f"8. Founder approved the refund; refund executed: ${result['refunded']:.2f} (test=true).",
        f"9. Download after refund: {after}.",
        f"10. Reconciliation: {summary['orders']} order(s), {summary['mismatches']} mismatch(es), "
        f"balanced={summary['balanced']}. See the reconciliation file (Phase 5, step 3).",
    ]
    run.write("payment_test_log.md", payment_test_log_md(run.id, steps))
    run.say("refund_done")
    run.save(Stage.PHASE6, status=Status.RUNNING)
