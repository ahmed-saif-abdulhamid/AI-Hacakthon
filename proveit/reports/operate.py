"""Phase 6 files: the persevere-or-pivot gate decision."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    pass


def operate_gate_md(outcome: str, reason: str, metrics: dict) -> str:
    lines = [
        "# Phase 6 gate: persevere or pivot",
        "",
        f"## Outcome: {outcome.upper()}",
        "",
        f"- **Reason:** {reason}",
        "- **Decided by:** code, from real records only (rule in phase6_step3_metrics.md)",
        f"- **Real sign-ups / real orders / test orders (excluded):** {metrics['real_signups']} / "
        f"{metrics['real_orders']} / {metrics['test_orders']}",
        "- **Status:** STUBBED (no live launch in this demo)",
        "",
    ]
    return "\n".join(lines)
