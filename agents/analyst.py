"""Analyst (Phase 6, STUBBED): the memo is written by code from real metrics only.

Interface for future work: ``memo(metrics, thresholds) -> str`` where metrics hold real
sign-ups, real orders, refunds and support requests. Test (MOCKED) orders never count.
"""
from __future__ import annotations

STATUS = "STUBBED"


def memo(metrics: dict, thresholds: dict) -> str:
    target = thresholds["gate2_demand"]["waitlist_target"]
    real = metrics.get("real_signups", 0)
    real_orders = metrics.get("real_orders", 0)
    lines = ["# Phase 6: Operate and learn memo (STUBBED)", "",
             "This memo uses real metrics only. MOCKED test orders and test sign-ups are excluded.", "",
             "| Metric | Value | Source |", "|---|---|---|",
             f"| Real waitlist sign-ups | {real} | signups table, test=false |",
             f"| Real orders | {real_orders} | orders table, test=false |",
             f"| Test orders (excluded) | {metrics.get('test_orders', 0)} | MOCKED payment test |",
             f"| Refunds | {metrics.get('refunds', 0)} | refunds table |", ""]
    if real < target and real_orders == 0:
        lines.append("**Not enough data to call persevere or pivot.** "
                     f"Real sign-ups ({real}) are below the pre-registered target ({target}) and there are no real orders.")
    else:
        lines.append("Metrics meet the minimum for a decision; the analyst model that would draft the memo is STUBBED.")
    return "\n".join(lines) + "\n"
