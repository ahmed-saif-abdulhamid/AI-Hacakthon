"""Phase 4 files: pricing and policy drafts."""

from __future__ import annotations

import re
from typing import TYPE_CHECKING

from .. import render
from ..models import Statement
from .common import preview_banner

if TYPE_CHECKING:
    from ..pipeline.run import Run


EMAIL = re.compile(r"[\w.+-]+@[\w-]+\.[\w.]+")


def pricing_md(run: Run, tiers: dict, rationale: list[Statement], prov: render.Provenance) -> str:
    ledger = run.ledger()
    used: list[str] = []
    label = "" if tiers["basis"] == "verified_price_points" else "ASSUMPTION: "
    points = ", ".join(f"${value:g} [{cid}]" for value, cid in tiers["points"]) or "none"
    lines = [
        "# Phase 4, step 1: Pricing",
        "",
        preview_banner(run),
        "| Tier | Price (USD, one-time) | Basis |",
        "|---|---|---|",
        f"| Good | {label}${tiers['good']:.0f} | {tiers['basis']} |",
        f"| Better | {label}${tiers['better']:.0f} | {tiers['basis']} |",
        f"| Best | {label}${tiers['best']:.0f} | {tiers['basis']} |",
        "",
        f"Verified price points used: {points}.",
        "",
        tiers["note"],
        "",
        "No revenue projections or scenarios are produced.",
        "",
        "## Rationale",
        "",
        render.render_list(rationale, ledger, used, prov, "phase4_step1_pricing.md"),
        "",
        render.sources_section(used, ledger),
    ]
    return "\n".join(lines)


def _policy_line(text: str) -> str:
    """No invented contact details: the founder fills in their own."""
    return render.label_unsourced_factual(EMAIL.sub("[founder's support email]", text))


def policies_md(policies, stamp: str, issue: str | None) -> str:
    lines = (
        ["# Phase 4, step 2: Policy drafts", "", f"**{stamp}**", "", "## Terms (DRAFT)", ""]
        + [f"- {_policy_line(x)}" for x in policies.terms]
        + [
            "",
            "## Privacy (DRAFT)",
            "",
            "What is stored: an email address and a timestamp for the waitlist; order records "
            "from the MOCKED payment test. No passwords and no card numbers are stored.",
            "",
        ]
        + [f"- {_policy_line(x)}" for x in policies.privacy]
        + [
            "",
            "## Refunds (DRAFT)",
            "",
            "Refund window: 14 days (ASSUMPTION, team default). Every refund is approved by the founder.",
            "",
        ]
        + [f"- {_policy_line(x)}" for x in policies.refunds]
        + [""]
    )
    if issue:
        lines.append(f"Flagged for founder review: {issue}\n")
    return "\n".join(lines)
