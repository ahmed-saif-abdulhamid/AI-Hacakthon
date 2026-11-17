"""Debate: an Advocate (best case for GO) and a Skeptic (best case for STOP).
Two short calls; both return Statements citing claim IDs. Code, not the debate, decides."""

from __future__ import annotations

from pydantic import BaseModel, Field

from proveit import llm
from proveit.models import Claim, Statement


class DebateOut(BaseModel):
    statements: list[Statement] = Field(min_length=1, max_length=3)


def claims_table(claims: list[Claim], limit: int = 14) -> str:
    rows = []
    for c in sorted(claims, key=lambda c: -c.weight)[:limit]:
        rows.append(f"{c.id} kind={c.kind} weight={c.weight} status={c.status} quote=\"{(c.quote or '')[:160]}\"")
    return "\n".join(rows) or "(no claims)"


def _metrics_line(metrics: dict) -> str:
    keep = ("sourced_pain", "distinct_sources", "recent_share", "wtp_signals", "competitors", "founder_fit", "coverage")
    return ", ".join(f"{k}={metrics.get(k)}" for k in keep)


def argue(
    run_id: str, side: str, claims: list[Claim], metrics: dict, variant_title: str, founder: str = ""
) -> list[Statement]:
    user = (
        f"VARIANT: {variant_title}\nFOUNDER: {founder or 'nothing known beyond the idea'}\n"
        f"METRICS: {_metrics_line(metrics)}\nCLAIMS:\n{claims_table(claims)}\nReturn 2 or 3 statements."
    )
    out = llm.agent_call(
        run_id,
        side,
        f"argue_{'go' if side == 'advocate' else 'stop'}",
        DebateOut,
        user,
        num_predict=220,
        sources=sorted({c.url for c in claims if c.url and c.weight > 0}),
    )
    return out.statements


def run(
    run_id: str, claims: list[Claim], metrics: dict, variant_title: str, founder: str = ""
) -> dict[str, list[Statement]]:
    return {
        "advocate": argue(run_id, "advocate", claims, metrics, variant_title, founder),
        "skeptic": argue(run_id, "skeptic", claims, metrics, variant_title, founder),
    }
