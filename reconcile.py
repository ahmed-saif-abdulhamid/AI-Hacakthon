"""Reconciliation (MOCKED data): matches orders, payments, fees, net and payouts, and
flags mismatches. Output: phase5_step3_reconciliation.csv."""

from __future__ import annotations

import csv
import io

from proveit import db
from proveit.log import log_action

COLUMNS = [
    "order_id",
    "order_amount",
    "payment_amount",
    "fee",
    "net",
    "payout_id",
    "payout_amount",
    "refund_amount",
    "order_status",
    "test",
    "check",
]


def run(run_id: str) -> tuple[str, dict]:
    rows, mismatches = [], 0
    for o in db.query("SELECT * FROM orders WHERE run_id=? ORDER BY created_at", (run_id,)):
        p = db.query_one("SELECT * FROM payments WHERE order_id=?", (o["id"],))
        po = db.query_one("SELECT * FROM payouts WHERE id=?", (p["payout_id"],)) if p else None
        rf = db.query_one("SELECT * FROM refunds WHERE order_id=?", (o["id"],))
        problems = []
        if p is None:
            problems.append("no_payment")
        else:
            if round(p["amount"], 2) != round(o["amount"], 2):
                problems.append("amount_mismatch")
            if round(p["amount"] - p["fee"], 2) != round(p["net"], 2):
                problems.append("net_mismatch")
            if po is None or round(po["amount"], 2) != round(p["net"], 2):
                problems.append("payout_mismatch")
        if o["status"] == "refunded" and rf is None:
            problems.append("refund_missing")
        mismatches += bool(problems)
        rows.append(
            {
                "order_id": o["id"],
                "order_amount": o["amount"],
                "payment_amount": p["amount"] if p else "",
                "fee": p["fee"] if p else "",
                "net": p["net"] if p else "",
                "payout_id": p["payout_id"] if p else "",
                "payout_amount": po["amount"] if po else "",
                "refund_amount": rf["amount"] if rf else 0,
                "order_status": o["status"],
                "test": "true",
                "check": "|".join(problems) or "matched",
            }
        )
    buf = io.StringIO()
    w = csv.DictWriter(buf, fieldnames=COLUMNS, lineterminator="\n")
    w.writeheader()
    w.writerows(rows)
    summary = {"orders": len(rows), "mismatches": mismatches, "balanced": mismatches == 0}
    log_action(run_id, "reconcile", "reconcile_orders_payments_payouts", test=True, **summary)
    return buf.getvalue(), summary
