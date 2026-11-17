"""Shared pieces of every report: the gate-decision summary and the preview banner."""

from __future__ import annotations

from typing import TYPE_CHECKING

from ..models import GateDecision

if TYPE_CHECKING:
    from ..pipeline.run import Run


def simple_gate_md(title: str, dec: GateDecision, extra: str = "") -> str:
    return (
        f"# {title}\n\n## Outcome: {dec.outcome.upper()}\n\n- **Reason:** {dec.reason}\n"
        f"- **Rule fired:** {dec.rule_fired}\n- **Next step:** {dec.next_step or '-'}\n"
        f"- **Recommendation:** {dec.recommendation}\n- **Founder decision:** {dec.founder_decision}\n"
        f"- **Thresholds SHA-256:** `{dec.thresholds_sha256}`\n\n## Metrics\n\n"
        + ("\n".join(f"- {k}: {v}" for k, v in dec.metrics.items()) or "- none: this gate is the founder's decision")
        + "\n\n## Thresholds\n\n"
        + ("\n".join(f"- {k}: {v}" for k, v in dec.thresholds.items()) or "- none")
        + "\n\n"
        + (
            "## Failed checks\n\n" + "\n".join(f"- {f}" for f in dec.failed_checks) + "\n\n"
            if dec.failed_checks
            else ""
        )
        + extra
    )


def preview_banner(run: Run) -> str:
    gates_over = run.state.get("overrides", [])
    if not gates_over:
        return ""
    names = " and ".join(g.replace("gate", "Gate ") for g in gates_over)
    return f"> PREVIEW after a founder override against the evidence at {names}: demand not yet proven.\n\n"
