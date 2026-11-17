"""Phase 3 files: product spec, checklist modules, CSV templates and the test report."""

from __future__ import annotations

import csv
import io
from typing import TYPE_CHECKING

from .. import render
from ..models import GateDecision

if TYPE_CHECKING:
    pass


def product_spec_md(spec, preview: str) -> str:
    lines = (
        [
            "# Phase 3, step 1: Product spec",
            "",
            preview + f"**Title:** {spec.title}",
            "",
            f"**Audience:** {spec.audience}",
            "",
            "## Modules",
            "",
        ]
        + [f"{i}. **{m.name}**: {m.purpose}" for i, m in enumerate(spec.modules, start=1)]
        + ["", "## What the product is not", ""]
        + [f"- {x}" for x in spec.not_included]
        + [""]
    )
    return render.label_unsourced_factual("\n".join(lines))


def module_md(module, preview: str) -> str:
    label = render.label_unsourced_factual
    lines = (
        [f"# {module.title}", "", preview + label(module.intro), "", "## Checklist", ""]
        + [f"- [ ] {label(step)}" for step in module.steps]
        + [""]
    )
    return "\n".join(lines)


def template_csv(module) -> str:
    """The module's CSV template; short rows are padded and long rows cut to the header's width."""
    width = len(module.template_columns)
    buf = io.StringIO()
    writer = csv.writer(buf, lineterminator="\n")
    writer.writerow(module.template_columns)
    for row in module.template_rows:
        writer.writerow((row + [""] * width)[:width])
    return buf.getvalue()


def test_report_md(dec: GateDecision, results: list[dict], attempts: int) -> str:
    lines = (
        [
            "# Phase 3 gate: test report",
            "",
            f"## Outcome: {dec.outcome.upper()}",
            "",
            "| Check | Passed | Detail |",
            "|---|---|---|",
        ]
        + [f"| {r['name']} | {'yes' if r['passed'] else 'no'} | {r['detail'][:80]} |" for r in results]
        + ["", f"All checks are deterministic code (no model). Build attempts: {attempts}.", ""]
    )
    return "\n".join(lines)
