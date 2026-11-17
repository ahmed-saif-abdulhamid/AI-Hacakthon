"""Phase 1 (Discover) and Gate 1 (evidence).

The Scout proposes angles, code ranks them, the chosen angle is researched, and code decides the gate
from pre-registered thresholds. The for-and-against debate only explains a decision; it never makes one.
"""

from __future__ import annotations

from agents import debate, scout

from ... import gates, llm, render
from ...log import emit, log_action
from ...models import GateDecision
from ...reports.discover import claims_json, gate1_md, interview_kit_md, market_md, opportunities_md
from .. import research
from ..run import PHASE_NAMES, Run, Stage, Status, log_gate, runtime

NO_DEBATE_REASONS = frozenset({"insufficient_evidence", "model_failure", "model_suspect"})
FOUNDER_CONTEXT_FIELDS = ("skills", "budget", "hours_per_week", "target_market", "values")


def _choose_variant(run: Run) -> None:
    """First visit only: the Scout's angles, ranked by code; the best eligible one is researched first."""
    variants = scout.run(run.id, run.brief)
    run.state["variants"] = [v.model_dump() for v in variants]
    run.progress(1, "Comparing the angles")
    ranking = research.score_alternatives(run, variants, run.thresholds["gate1_evidence"]["max_age_months"])
    run.state["ranking"] = ranking
    chosen = next((r["n"] for r in ranking if r.get("chosen")), 1)
    run.state["variant_n"] = chosen
    run.write("phase1_step1_opportunities.md", opportunities_md(run, variants))
    run.say("variants", title=run.variant(chosen).title)
    run.save()


def _research_current(run: Run, variant_n: int, repeats: int) -> dict:
    """Research the current angle once per (variant, repeat). A retry after a pause (for example a rate
    limit at the debate) reuses the search already made, so quotes are never counted twice."""
    done_key = f"{variant_n}:{repeats}"
    if run.state.get("research_done") == done_key and str(variant_n) in run.state.get("research", {}):
        return run.state["research"][str(variant_n)]
    record = research.research_variant(run, run.variant(variant_n), broaden=repeats > 0)
    run.state.setdefault("claims", []).extend(record.pop("claims"))
    run.state.setdefault("research", {})[str(variant_n)] = record
    run.state["research_done"] = done_key
    run.save()
    return record


def _research_other_variants(run: Run, variant_n: int) -> None:
    """Full mode also researches the other top angles, for comparison only."""
    if run.mode != "full" or run.state.get("others_researched"):
        return
    n_researched = min(runtime()[run.mode]["variants_researched"], len(run.state["variants"]))
    for n in range(1, n_researched + 1):
        if n == variant_n:
            continue
        record = research.research_variant(run, run.variant(n))
        run.state["claims"].extend(record.pop("claims"))
        run.state["research"][str(n)] = record
    run.state["others_researched"] = True


def _founder_context(run: Run) -> str:
    known = {
        k: v
        for k, v in run.state.get("brief", {}).items()
        if k in FOUNDER_CONTEXT_FIELDS and v and "unspecified" not in str(v)
    }
    return "; ".join(f"{k.replace('_', ' ')}: {v}" for k, v in known.items())


def _debate(run: Run, dec: GateDecision, claims: list, metrics: dict, variant_n: int) -> dict:
    """Arguments for and against the gate's decision; skipped when there is nothing to argue about
    (the sources could not see the market, or the research failed)."""
    arguments: dict = {"advocate": [], "skeptic": []}
    run.state.pop("debate", None)
    if dec.reason in NO_DEBATE_REASONS:
        return arguments
    run.progress(1, "Weighing the case for and against")
    try:
        arguments = debate.run(run.id, claims, metrics, run.variant(variant_n).title, _founder_context(run))
    except llm.LLMError as e:
        log_action(run.id, "orchestrator", "debate_skipped_model_unavailable", error=str(e)[:160])
        return arguments
    run.state["debate"] = {side: [s.model_dump() for s in points] for side, points in arguments.items()}
    run.say(
        "debate",
        advocate=arguments["advocate"][0].text if arguments["advocate"] else "",
        skeptic=arguments["skeptic"][0].text if arguments["skeptic"] else "",
    )
    return arguments


def _write_phase1_files(run: Run, dec: GateDecision, claims: list, arguments: dict, record: dict) -> None:
    variant = run.variant()
    prov = render.Provenance()
    run.write("phase1_gate_decision.md", gate1_md(run, dec, claims, arguments, prov))
    run.write("phase1_step3_market.md", market_md(run, variant, claims, record.get("wiki")))
    run.write("phase1_step4_interview-kit.md", interview_kit_md(run, variant, dec))
    prov.write(run.dir)


def _next_stage(run: Run, dec: GateDecision, repeats: int) -> None:
    max_repeats = run.thresholds["gate1_evidence"]["max_repeats"]
    if (
        dec.outcome == "repeat"
        and dec.reason == "near_miss"
        and runtime()[run.mode]["auto_rerun"]
        and repeats < max_repeats
    ):
        run.state["repeats"] = repeats + 1
        run.save(Stage.PHASE1)
    elif dec.outcome == "go":
        run.save(Stage.PHASE2, outcome="go")
    elif dec.outcome == "stop":
        run.save(Stage.STOPPED, outcome="stop", status=Status.STOPPED)
    else:
        run.state["waiting_for"] = "gate1_decision"
        run.save(Stage.AWAIT_FOUNDER, outcome=dec.outcome, status=Status.WAITING)


def stage_phase1(run: Run) -> None:
    run.progress(1, "Phase 1: Discover")
    run.say("phase", n=1, name=PHASE_NAMES[1])
    if "variants" not in run.state:
        _choose_variant(run)
    variant_n = run.state.get("variant_n", 1)
    repeats = run.state.get("repeats", 0)
    record = _research_current(run, variant_n, repeats)
    _research_other_variants(run, variant_n)
    run.write("phase1_step2_claims.json", claims_json(run))

    claims = [c for c in run.claims() if c.hit_id in record["hits"]]
    metrics = record["metrics"]
    dec = gates.evaluate_gate1(
        run.id,
        metrics,
        run.thresholds,
        run.brief_raw,
        run.sha,
        model_failure=record["model_failure"],
        missed=record["missed"],
        repeats=repeats,
        variant_n=variant_n,
        n_variants=len(run.state["variants"]),
        next_variant=run.next_variant(),
    )
    arguments = _debate(run, dec, claims, metrics, variant_n)
    if dec.goalpost_moved:
        log_action(run.id, "gatekeeper", "goalpost_moved", goalpost_moved=True)
    log_gate(
        run,
        "evidence_gate",
        dec,
        sources=sorted({c.url for c in claims if c.weight > 0}),
        thresholds_sha256=dec.thresholds_sha256,
        goalpost_moved=dec.goalpost_moved,
    )
    if dec.outcome == "stop" and run.mode == "live" and len(run.state["variants"]) > 1:
        dec.recommendation += f" (STOP for variant {variant_n}; the other angles were scored but not researched.)"
    run.state["gate1"] = dec.model_dump()
    run.say("gate", **dec.model_dump())
    _write_phase1_files(run, dec, claims, arguments, record)
    emit(run.id, 1, "gate", dec.outcome, gate="gate1_evidence", reason=dec.reason, rule=dec.rule_fired)
    _next_stage(run, dec, repeats)
