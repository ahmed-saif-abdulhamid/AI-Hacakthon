"""Report writers: every Markdown and JSON file a run produces, built from run state by code.

The orchestrator decides what happens; this module only formats what was decided, so the
files in ``outputs/`` read the same whichever stage wrote them.
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

from . import gates, render, verifier
from .models import Claim, GateDecision, Statement, Variant

if TYPE_CHECKING:
    from .orchestrator import Run


def eligibility_md(dec: GateDecision, res) -> str:
    return (
        f"# Phase 1 gate: eligibility\n\n**Outcome:** {dec.outcome.upper()}\n\n**Reason:** {dec.reason}\n\n"
        f"**Rule fired:** {res.rule} ({res.layer})\n\n**Matched:** `{res.matched or ''}`\n\n"
        f"**Explanation:** {res.message}\n\n**Thresholds SHA-256:** `{dec.thresholds_sha256}`\n"
    )


def opportunities_md(run: Run, variants: list[Variant]) -> str:
    fit, parts = gates.founder_fit(run.brief)
    lines = [
        "# Phase 1, step 1: Opportunities",
        "",
        f"**Founder idea:** {run.brief.idea}",
        "",
        f"**Founder fit (computed in code from the brief, 0-5):** {fit}  ",
        "Components: " + ", ".join(f"{k}={v}" for k, v in parts.items()) + " (unspecified fields count 0.5).",
        "",
        "| # | Variant | Segment | Job to be done | Pain queries | Competitor query | SE site |",
        "|---|---|---|---|---|---|---|",
    ]
    for v in variants:
        lines.append(
            f"| {v.n} | {v.title} | {v.segment} | {v.job_to_be_done} | {'; '.join(v.pain_queries)} | "
            f"{v.competitor_query} | {v.se_site} |"
        )
    lines += ["", "Variants are proposals from the Scout model and are research targets, not market claims.", ""]
    ranking = run.state.get("ranking") or []
    if any("signal" in r for r in ranking):
        g = run.state["thresholds"]["gate1_evidence"]
        lines += [
            "## Scored against each other (code only, before deep research)",
            "",
            f"Each angle's pain queries were run against Hacker News comments from the last {g['max_age_months']} months "
            f"(https://hn.algolia.com/api/v1/search). Code counted comments that are on topic and read as the "
            "writer's own complaint (first person, a pain cue, not a product pitch). Fit is the share of the "
            "angle's segment and job words found in the founder's skills, market and idea.",
            "",
            "| # | Variant | Comments checked | On topic | First-person complaints | Founder fit | Signal | Researched first |",
            "|---|---|---|---|---|---|---|---|",
        ]
        for r in sorted(ranking, key=lambda r: -r.get("signal", -1)):
            if r.get("excluded"):
                lines.append(f"| {r['n']} | {r['title']} | - | - | - | - | - | never: {r['excluded']} |")
                continue
            lines.append(
                f"| {r['n']} | {r['title']} | {r['comments_checked']} | {r['on_topic']} | {r['complaints']} | "
                f"{r['fit']} | {r['signal']} | {'**yes**' if r.get('chosen') else 'pivot target'} |"
            )
        lines += [
            "",
            "Signal = complaints + 0.25 x on-topic comments + 2 x fit. ASSUMPTION: these weights are a team "
            "default; the counts only rank the angles and are never counted as evidence at a gate. "
            "The deep research below (step 2) is what Gate 1 reads.",
            "",
        ]
    else:
        lines += [f"Variant {run.state.get('variant_n', 1)} is researched first.", ""]
    return "\n".join(lines)


def claims_json(run: Run) -> str:
    data = {
        "run_id": run.id,
        "thresholds_sha256": run.sha,
        "note": (
            "quotes are extracted by code from the source record and re-checked against the public page where "
            "reachable; a claim counts only if code confirms it is on-topic and contains a pain or payment cue."
        ),
        "claims": [],
        "source_calls": {},
    }
    for c in run.claims():
        d = c.model_dump(mode="json")
        d.pop("run_id", None)
        data["claims"].append(d)
    for n, r in run.state.get("research", {}).items():
        data["source_calls"][f"variant_{n}"] = r.get("coverage_rows", [])
    return json.dumps(data, indent=2, ensure_ascii=False)


def claim_table(claims: list[Claim]) -> str:
    rows = ["| ID | Kind | Status | Weight | Cue | Quote | Source |", "|---|---|---|---|---|---|---|"]
    for c in sorted(claims, key=lambda c: (-c.weight, c.id)):
        quote = (c.quote or "").replace("|", "/")
        quote = quote[:220] + ("..." if len(quote) > 220 else "")
        label = (
            c.status.upper()
            if c.weight > 0
            else ("ASSUMPTION" if c.label == "ASSUMPTION" else c.status + " (weight 0)")
        )
        rows.append(
            f"| {c.id} | {c.kind} | {label} | {c.weight} | {c.cue_matched or '-'} | \"{quote}\" "
            f"{('<br>' + c.weight_note) if c.weight_note else ''} | {c.url or 'ASSUMPTION'} |"
        )
    return "\n".join(rows)


def plain_summary(dec: GateDecision) -> str:
    """One founder-readable sentence at the top of every gate file (the exact figures follow below)."""
    m, g = dec.metrics or {}, dec.thresholds or {}
    pain, need = m.get("sourced_pain"), g.get("min_sourced_pain")
    if dec.outcome == "go":
        return "Enough people describe this problem in their own words, from more than one place. Worth taking further."
    if dec.reason in ("model_failure", "model_suspect"):
        return "The research didn't come back clean, so no verdict was given on the idea. Search again."
    if dec.outcome == "repeat" and dec.reason == "insufficient_evidence":
        return (
            "The public forums searched can't see this market well enough to call it either way. That is not "
            "proof nobody wants it: the next step is five short conversations (see the interview kit)."
        )
    if dec.outcome == "repeat":
        return "Close to the bar. A wider search could tip it either way."
    if dec.outcome == "pivot":
        return "The problem looks real, but this version of the idea doesn't fit it. Try another angle."
    if pain is not None and need is not None:
        n = int(round(pain))
        found = "no one clearly describing the problem" if n == 0 else f"{n} real complaint{'s' if n != 1 else ''}"
        return (
            f"People discuss this topic, but ProveIt found {found}, against the {need} it set as the bar before "
            "searching. Recommendation: don't build this as it stands."
        )
    return dec.recommendation


def gate1_md(run: Run, dec: GateDecision, claims: list[Claim], args: dict, prov: render.Provenance) -> str:
    ledger = run.ledger()
    used: list[str] = []
    g = dec.thresholds
    m = dec.metrics
    rows = [
        ("sourced_pain (weighted)", m.get("sourced_pain"), f">= {g['min_sourced_pain']}"),
        ("distinct_sources", m.get("distinct_sources"), f">= {g['min_distinct_sources']}"),
        (
            "recent_share (<= {} months)".format(g["max_age_months"]),
            m.get("recent_share"),
            f">= {g['min_recent_share']}",
        ),
        ("wtp_signals", m.get("wtp_signals"), f">= {g['min_wtp_signals']}"),
        ("competitors (distinct, verified)", m.get("competitors"), f"in {g['competitor_band']}"),
        ("founder_fit (0-5, code)", m.get("founder_fit"), f">= {g['min_founder_fit']}"),
        ("coverage", m.get("coverage"), f">= {g['min_coverage']}"),
    ]
    out = [
        "# Phase 1 gate: evidence decision",
        "",
        f"## Outcome: {dec.outcome.upper()}",
        "",
        f"> **In plain words:** {plain_summary(dec)}",
        "",
        f"- **Reason:** {dec.reason}",
        f"- **Rule fired:** {dec.rule_fired}",
        f"- **Next step:** {dec.next_step or '-'}",
        f"- **Recommendation:** {dec.recommendation}",
        f"- **Variant researched:** {run.variant().n}. {run.variant().title}",
        f"- **Pre-registered thresholds SHA-256:** `{dec.thresholds_sha256}`",
        f"- **Goalpost moved:** {str(dec.goalpost_moved).lower()}",
        f"- **Founder decision:** {dec.founder_decision}",
        "",
        "Thresholds are team defaults (ASSUMPTION), registered before any source was called.",
        "",
        "## Metrics vs thresholds",
        "",
        "| Check | Value | Threshold | Pass |",
        "|---|---|---|---|",
    ]
    for name, val, thr in rows:
        key = name.split(" ")[0]
        key = "competitor_band" if key == "competitors" else key
        out.append(f"| {name} | {val} | {thr} | {'no' if key in dec.failed_checks else 'yes'} |")
    out += [
        "",
        f"Claims: {m.get('claims_total', 0)} total, {m.get('claims_verified_live', 0)} verified live, "
        f"{m.get('claims_archived', 0)} archived matches, {m.get('claims_unverified', 0)} unverified.",
        "",
    ]
    research = run.state.get("research", {}).get(str(run.variant().n), {})
    if research.get("missed"):
        out.append(f"Code-qualified sentences not selected by the model: {', '.join(research['missed'])}.\n")
    if args.get("advocate") or args.get("skeptic"):
        out += [
            "## Advocate (case for GO)",
            "",
            render.render_list(
                [Statement(**s) if isinstance(s, dict) else s for s in args["advocate"]],
                ledger,
                used,
                prov,
                "phase1_gate_decision.md",
            ),
            "",
            "## Skeptic (case for STOP)",
            "",
            render.render_list(
                [Statement(**s) if isinstance(s, dict) else s for s in args["skeptic"]],
                ledger,
                used,
                prov,
                "phase1_gate_decision.md",
            ),
            "",
            "The arguments are model-written and decide nothing; `gates.py` applies the rule precedence.",
            "",
        ]
    else:
        out += [
            "## For and against",
            "",
            "Not written for this verdict: the public sources gave too little to argue about, or the research "
            "did not come back clean. The arguments never decide a checkpoint.",
            "",
        ]
    out += [
        "## Source coverage",
        "",
        "| Source | Query | OK | Hits | On-topic | Covered |",
        "|---|---|---|---|---|---|",
    ]
    for r in research.get("coverage_rows", []):
        out.append(
            f"| {r['source']} | {r['query']} | {r['ok']} | {r['hits']} | {r['on_topic']} | {r['covered']} |"
            + (f" {r['error'][:60]}" if r.get("error") else "")
        )
    out += ["", "## Claim ledger (this variant)", "", claim_table(claims), "", render.sources_section(used, ledger)]
    return "\n".join(out)


def market_md(run: Run, variant: Variant, claims: list[Claim], wiki: dict | None) -> str:
    comps = [c for c in claims if c.kind == "competitor" and c.weight > 0]
    prices = [c for c in claims if c.kind == "price_point" and c.weight > 0]
    lines = [
        "# Phase 1, step 3: Market definition",
        "",
        f"**Segment:** {variant.segment} (from the Scout variant; a research target, not a market claim)",
        "",
        f"**Job to be done:** {variant.job_to_be_done}",
        "",
        "## Alternatives and competitors (verified claims only)",
        "",
    ]
    lines += [f'- [{c.id}] "{c.quote}" ({c.url})' for c in comps] or [
        "- ASSUMPTION: no verified competitor claim in the ledger for this variant."
    ]
    lines += ["", "## Visible prices", ""]
    lines += [f'- [{c.id}] "{c.quote}" ({c.url})' for c in prices] or [
        "- ASSUMPTION: no verified price point in the ledger for this variant."
    ]
    lines += [
        "",
        "## Market size",
        "",
        "ASSUMPTION: no source in the ledger states a market size, so no TAM/SAM figure is given.",
        "",
    ]
    if wiki and verifier.is_on_topic(
        f"{wiki.get('title', '')} {wiki.get('extract', '')}", verifier.topic_keywords(variant)
    ):
        lines += [
            "## Context (Wikipedia, context only, never evidence)",
            "",
            f"{wiki['extract']}",
            "",
            f"Source: {wiki['url']}",
            "",
        ]
    return "\n".join(lines)


def interview_kit_md(run: Run, variant: Variant, dec: GateDecision) -> str:
    seg, job = variant.segment, variant.job_to_be_done
    qs = [
        f"Tell me about the last time you had to {job.lower().rstrip('.')}. What happened?",
        "What was the hardest part of that, and why?",
        "What did you do about it? What tools, templates or people did you use?",
        "What did that cost you, in money or time, the last time?",
        "Have you looked for a better way? What did you find, and why did you not keep using it?",
        "When did this last come up, and how often has it come up in the past three months?",
        "Who else is involved when this happens?",
        "Is there anything else about this I should have asked?",
    ]
    lines = [
        "# Phase 1, step 4: Mom Test interview kit",
        "",
        f"For: {seg}. Questions are about past behaviour only (no hypotheticals, no pitching).",
        "",
        "## Questions",
        "",
    ] + [f"{i}. {q}" for i, q in enumerate(qs, start=1)]
    lines += [
        "",
        "## Who to talk to (screener)",
        "",
        f"- They are one of: {seg}.",
        f"- They had to {job.lower().rstrip('.')} at least once in the past three months.",
        "- They are not a friend or family member (polite answers are not evidence).",
        "",
        "## How to decide after five conversations",
        "",
        "- **Strong signal:** 3 or more of 5 describe a recent, specific time it went wrong AND already spend "
        "money or real time on a workaround. Carry on to the waiting-list test.",
        "- **Weak signal:** 1-2 of 5 do. Try another angle (a different segment or job).",
        "- **No signal:** nobody can name a recent instance. Stop here; it saved you the build.",
        '- Ask about the past only. Compliments and "I would buy that" don\'t count.',
        "",
    ]
    lines += [
        "## Notes template",
        "",
        "| Interviewee profile | Date | Last time it happened | Workaround used | "
        "Money/time spent | Strong signal? |",
        "|---|---|---|---|---|---|",
        "| | | | | | |",
        "",
    ]
    if dec.outcome == "repeat" and dec.reason == "insufficient_evidence" or dec.next_step == "mom_test_interviews":
        market = run.brief.target_market if "unspecified" not in run.brief.target_market else "your target region"
        lines += [
            "## 5-interview plan (the gate said REPEAT: insufficient evidence)",
            "",
            "Profiles to find, not named people:",
            "",
            f"1. 2 {seg} in {market} who did this job in the past month; ask in local professional groups.",
            f"2. 1 {seg} who pays for a tool or service for this job today; find them via the tool's community forum.",
            f"3. 1 {seg} who stopped doing this job themselves; ask in the {variant.se_site} Stack Exchange community.",
            f"4. 1 person who hires or works with {seg}; ask in your own network.",
            "",
            "Interview-notes analysis is STUBBED; record answers in the notes template.",
            "",
        ]
    return "\n".join(lines)


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
