"""Run the guard eval sets and write evals/results.md.

  python -m evals.run_evals            rules only + model layer (needs the local model)
  python -m evals.run_evals --rules    rules only
Numbers are on our own eval sets only; they are not a general safety claim.
"""

from __future__ import annotations

import argparse
import time
from pathlib import Path

import yaml

from proveit import guard, llm

EV = Path(__file__).resolve().parent


def _load(name: str) -> list[dict]:
    return yaml.safe_load((EV / name).read_text(encoding="utf-8"))


def _evaluate(items: list[dict], default_scope: str, must_block: bool, use_model: bool) -> list[dict]:
    """Run each prompt through the rules alone and through rules + model; record whether each was right."""

    def correct(res: guard.GuardResult) -> bool:
        return res.blocked if must_block else res.verdict == "allow"

    rows = []
    for it in items:
        scope = it.get("scope", default_scope)
        r_rules = guard.check_input(it["prompt"], scope=scope, use_model=False)
        r_full = guard.check_input(it["prompt"], scope=scope, use_model=True) if use_model else r_rules
        rows.append(
            {
                "id": it["id"],
                "layer": it.get("layer", ""),
                "prompt": it["prompt"],
                "rules": correct(r_rules),
                "full": correct(r_full),
                "rule": r_full.rule or r_rules.rule or "",
                "via": r_full.layer or "",
            }
        )
    return rows


def run(use_model: bool) -> dict:
    """Every eval set's rows, the model used (if any) and the run time."""
    t0 = time.time()
    rows = {
        "must_refuse": _evaluate(_load("trick_prompts.yaml"), "ask", True, use_model),
        "must_pass": _evaluate(_load("benign_briefs.yaml"), "brief", False, use_model),
        "heldout": _evaluate(_load("trick_prompts_heldout.yaml"), "ask", True, use_model),
    }
    return {
        "model": llm.model_name() if use_model else None,
        "rows": rows,
        "seconds": round(time.time() - t0, 1),
    }


def write(res: dict) -> str:
    def pct(rows, key, flt=lambda r: True):
        sel = [r for r in rows if flt(r)]
        return f"{sum(r[key] for r in sel)}/{len(sel)}"

    r = res["rows"]
    lines = [
        "# Guard eval results",
        "",
        "Measured on our own eval sets (not a general safety claim). `rules` = deterministic rules only; "
        f"`rules + model` adds the model policy check ({res['model'] or 'not run'}).",
        "",
        "| Set | rules | rules + model |",
        "|---|---|---|",
        f"| Must-refuse, rules_only subset (CI requires 100%) | {pct(r['must_refuse'], 'rules', lambda x: x['layer'] == 'rules_only')} | {pct(r['must_refuse'], 'full', lambda x: x['layer'] == 'rules_only')} |",
        f"| Must-refuse, llm_layer subset (reported) | {pct(r['must_refuse'], 'rules', lambda x: x['layer'] == 'llm_layer')} | {pct(r['must_refuse'], 'full', lambda x: x['layer'] == 'llm_layer')} |",
        f"| Must-pass briefs (allowed) | {pct(r['must_pass'], 'rules')} | {pct(r['must_pass'], 'full')} |",
        f"| Held-out tricks (never used for tuning) | {pct(r['heldout'], 'rules')} | {pct(r['heldout'], 'full')} |",
        "",
        "The held-out set was written after the rules were frozen, by the same author as the rules; it has "
        "not been used to change any rule. Misses are listed below and left as they are.",
        "",
        "## Misses",
        "",
    ]
    for name, rows in r.items():
        for x in rows:
            if not x["full"]:
                lines.append(f"- {name} {x['id']}: \"{x['prompt']}\" (rules: {'hit' if x['rules'] else 'miss'})")
    lines += ["", f"Run time: {res['seconds']} s.", ""]
    text = "\n".join(lines)
    (EV / "results.md").write_text(text, encoding="utf-8", newline="\n")
    return text


def main() -> None:
    ap = argparse.ArgumentParser(prog="python -m evals.run_evals")
    ap.add_argument("--rules", action="store_true", help="rules only (no model needed)")
    print(write(run(use_model=not ap.parse_args().rules)))


if __name__ == "__main__":
    main()
