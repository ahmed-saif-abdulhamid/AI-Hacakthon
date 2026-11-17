"""Outward copy (landing page, store page, launch post, policies) passes the guard before the founder sees it.

Each draft is checked by rule set C, the model check and the market-statement rule. A blocked draft is
regenerated once with the violation named; if it is still blocked, code removes the parts the guard
blocks and anything left is flagged for the founder.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import TypeVar

from .. import guard, llm, render
from ..log import log_action
from .run import Run

T = TypeVar("T")
ATTEMPTS = 2
ISSUE_CHARS = 200


def guarded(
    run: Run, artifact: str, generate: Callable[[str], T], to_text: Callable[[T], str], scope: str = "outward"
) -> tuple[T, str | None]:
    """Generate copy with ``generate(feedback)``; return it and the unresolved issue (None when clean)."""
    draft = generate("")
    issue = None
    for attempt in range(1, ATTEMPTS + 1):
        text = to_text(draft)
        res = guard.check_output(text, scope, use_model=True, run_id=run.id)
        unsourced = render.factual_flags(text)
        if not res.blocked and not unsourced:
            log_action(
                run.id, "guard", f"check_{artifact}", model=llm.model_name(), cost=0, verdict="allow", attempt=attempt
            )
            return draft, None
        issue = res.message if res.blocked else "unsourced market statement: " + "; ".join(unsourced)[:ISSUE_CHARS]
        log_action(
            run.id,
            "guard",
            "guard_block",
            model=llm.model_name() if res.layer == "model" else None,
            cost=0,
            artifact=artifact,
            rule=res.rule or "unsourced_market_statement",
            attempt=attempt,
        )
        if attempt < ATTEMPTS:
            draft = generate(issue)
    return draft, issue


def is_blocked(text: str) -> bool:
    """The rule-based outward check alone (no model), used to filter individual sentences."""
    return guard.check_output(text, "outward").blocked


def drop_blocked(run: Run, artifact: str, parts: list[T], to_text: Callable[[T], str] = str) -> list[T]:
    """Keep only the parts the guard allows, logging how many were dropped."""
    kept = [p for p in parts if not is_blocked(to_text(p))]
    if len(kept) < len(parts):
        log_action(run.id, "guard", "drop_blocked_copy", artifact=artifact, dropped=len(parts) - len(kept))
    return kept


def flag_for_founder(run: Run, artifact: str, state_key: str, issue: str) -> None:
    log_action(run.id, "guard", "flag_for_founder", artifact=artifact, issue=issue[:ISSUE_CHARS])
    run.state[state_key] = issue
