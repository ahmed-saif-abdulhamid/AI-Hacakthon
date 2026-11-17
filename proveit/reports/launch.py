"""Phase 5 files: the launch-post draft and the MOCKED payment test log."""

from __future__ import annotations

from typing import TYPE_CHECKING

from .. import render
from .common import preview_banner

if TYPE_CHECKING:
    from ..pipeline.run import Run


def launch_post_md(run: Run, title: str, body: str, issue: str | None) -> str:
    return (
        "# DRAFT - NOT POSTED. For the founder to post under their own name.\n\n"
        + preview_banner(run)
        + f"## {title}\n\n{render.label_unsourced_factual(body)}\n\n"
        + (f"Flagged for founder review: {issue}\n\n" if issue else "")
        + "Posting adapters are STUBBED; publish_post is gated and raises NotEnabled.\n"
    )


def payment_test_log_md(run_id: str, steps: list[str]) -> str:
    lines = [
        "# Payment and delivery test log (MOCKED)",
        "",
        "Everything below ran through the in-process MockPaymentProvider. No real or sandbox payment was made, "
        "no card details exist anywhere, and every order is test=true and excluded from every gate.",
        "",
        f"Run: `{run_id}`",
        "",
        *steps,
        "",
    ]
    return "\n".join(lines)
