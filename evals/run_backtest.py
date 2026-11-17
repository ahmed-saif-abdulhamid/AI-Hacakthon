"""Run the Gate 1 calibration set against the real model and write evals/gate_backtest.md.

Usage:  python -m evals.run_backtest            (about 10 x 8 model calls, a few minutes on NVIDIA's free tier)
Every run is a normal live-mode Phase 1 run, logged like any other; nothing is tuned to the results.
"""

from __future__ import annotations

import time
from collections import Counter
from pathlib import Path

import yaml

from proveit import llm, orchestrator

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "evals" / "gate_backtest.md"
PAUSE_BETWEEN_IDEAS_SECONDS = 3  # stay well inside the free tier's rate limit
# The same founder facts for every idea, so only the idea and its market differ between runs.
FOUNDER_FIELDS = {"skills": "unspecified", "hours_per_week": "8", "budget": "$100", "values": "honest"}


def main() -> None:
    ideas = yaml.safe_load((ROOT / "evals" / "backtest_ideas.yaml").read_text(encoding="utf-8"))["ideas"]
    rows = []
    for it in ideas:
        rows.append(_run_idea(it))
        time.sleep(PAUSE_BETWEEN_IDEAS_SECONDS)
    write(rows)


def _run_idea(it: dict) -> dict:
    """One live Phase 1 run for a calibration idea, reduced to the Gate 1 outcome and its numbers."""
    t0 = time.time()
    fields = {"idea": it["idea"], "target_market": it["target_market"], **FOUNDER_FIELDS}
    rid = orchestrator.start("", fields, mode="live", label="backtest")
    orchestrator.advance(rid)
    g = orchestrator.load(rid).state.get("gate1") or {}
    m = g.get("metrics") or {}
    return {
        **it,
        "run": rid,
        "actual": g.get("outcome", "error"),
        "rule": g.get("rule_fired", ""),
        "pain": m.get("sourced_pain"),
        "coverage": m.get("coverage"),
        "sources": m.get("distinct_sources"),
        "payers": m.get("wtp_signals"),
        "competitors": m.get("competitors"),
        "seconds": round(time.time() - t0),
        "calls": llm.usage(rid).get("calls"),
    }


def write(rows: list[dict]) -> None:
    """Write the results table and confusion matrix to evals/gate_backtest.md and print them."""
    labels = ["go", "pivot", "repeat", "stop"]
    cm = Counter((r["expected"], r["actual"]) for r in rows)
    agree = sum(1 for r in rows if r["expected"] == r["actual"])
    lines = [
        "# Gate 1 calibration run",
        "",
        f"Model: `{llm.model_name()}` on NVIDIA's free tier. Live mode (variant 1 only). Thresholds unchanged "
        "(`config/gates.yaml`). The expected outcome for each idea was written before the run and is an "
        "ASSUMPTION (an informed prior, not ground truth).",
        "",
        f"**Agreement with the prior: {agree} of {len(rows)}.** Median time to a verdict: "
        f"{sorted(r['seconds'] for r in rows)[len(rows) // 2]} s.",
        "",
        "| Idea | Expected (ASSUMPTION) | Gate 1 | Rule | Complaints counted | Coverage | Places | People who'd pay | Competitors | Time | Run |",
        "|---|---|---|---|---|---|---|---|---|---|---|",
    ]
    for r in rows:
        lines.append(
            f"| {r['id']} | {r['expected']} | **{r['actual']}** | {r['rule']} | {r['pain']} | {r['coverage']} | "
            f"{r['sources']} | {r['payers']} | {r['competitors']} | {r['seconds']} s | `{r['run']}` |"
        )
    lines += [
        "",
        "## Confusion matrix (rows: expected, columns: gate)",
        "",
        "| expected \\ gate | " + " | ".join(labels) + " |",
        "|---|" + "---|" * len(labels),
    ]
    for e in labels:
        lines.append(f"| {e} | " + " | ".join(str(cm.get((e, a), 0)) for a in labels) + " |")
    lines += [
        "",
        "## Reading it",
        "",
        "- The gate is deliberately conservative: it never says GO on silence or on product launches alone; "
        "it needs people describing the problem in their own words, from at least two places.",
        "- REPEAT means the public sources can't see the market well enough; the next step is the 5-interview "
        "kit, not a verdict on the idea.",
        "- Disagreements are listed as they happened; no threshold or rule was changed to make them agree.",
        "",
    ]
    OUT.write_text("\n".join(lines), encoding="utf-8", newline="\n")
    print("\n".join(lines))


if __name__ == "__main__":
    main()
