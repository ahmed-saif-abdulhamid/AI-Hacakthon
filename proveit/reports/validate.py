"""Phase 2 files: the Lean Canvas and the demand-gate note."""

from __future__ import annotations

from typing import TYPE_CHECKING

from .. import render
from ..models import Variant

if TYPE_CHECKING:
    from ..pipeline.run import Run


GATE2_NOTE = (
    "Test sign-ups are excluded from every gate while public hosting is STUBBED. "
    "Continuing past this gate needs a logged founder override; Phases 3-5 are then a preview: "
    "demand not yet proven.\n"
)


def lean_canvas_md(run: Run, variant: Variant, canvas, cells: list[str], prov: render.Provenance) -> str:
    fname = "phase2_step1_lean-canvas.md"
    ledger = run.ledger()
    used: list[str] = []
    demand = run.thresholds["gate2_demand"]
    lines = [
        "# Phase 2, step 1: Lean Canvas",
        "",
        f"Variant: {variant.title}",
        "",
        "Each statement cites verified claim IDs or is labelled ASSUMPTION by code.",
        "",
    ]
    for cell in cells:
        lines += [
            f"## {cell.replace('_', ' ').title()}",
            "",
            render.render_list(getattr(canvas, cell), ledger, used, prov, fname),
            "",
        ]
    lines += [
        "## Riskiest assumption",
        "",
        render.render_list([canvas.riskiest_assumption], ledger, used, prov, fname),
        "",
        "## Experiment",
        "",
        render.render_list([canvas.experiment], ledger, used, prov, fname),
        "",
        f"Pre-registered demand target: {demand['waitlist_target']} waitlist "
        f"sign-ups in {demand['window_days']} days (team default, ASSUMPTION).",
        "",
        render.sources_section(used, ledger),
    ]
    return "\n".join(lines)
