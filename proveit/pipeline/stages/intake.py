"""Intake: the eligibility check on the founder's brief, then the brief is structured by the Intake agent.

An excluded product category or a guard refusal stops the run before any research. A word that only
might mean an excluded category asks the founder to confirm first (``await_clarify``).
"""

from __future__ import annotations

from agents import intake

from ... import guard, llm
from ...log import emit, log_action
from ...models import GateDecision
from ...reports import eligibility_md
from ..run import Run, Stage, Status


def _brief_text(run: Run) -> str:
    fields = "\n".join(f"{k}: {v}" for k, v in run.brief_raw["fields"].items())
    return run.brief_raw["text"] + "\n" + fields


def _stop(run: Run, res) -> None:
    excluded_category = res.verdict == "stop"
    dec = GateDecision(
        run_id=run.id,
        gate="phase1_eligibility",
        outcome="stop",
        reason="excluded_category" if excluded_category else "guard_refusal",
        rule_fired=res.rule or "",
        thresholds_sha256=run.sha,
        recommendation=res.message,
        failed_checks=[res.rule or ""],
    )
    run.write("phase1_gate_eligibility.md", eligibility_md(dec, res))
    log_action(run.id, "gatekeeper", "eligibility_gate", outcome="stop", reason=dec.reason, rule_fired=res.rule)
    if excluded_category:
        run.say("gate", outcome="stop", reason="excluded_category")
    else:
        run.say("refusal", rule=res.rule, message=res.message)
    run.state["gate1"] = dec.model_dump()
    run.save(Stage.STOPPED, outcome="stop", status=Status.STOPPED)


def stage_intake(run: Run) -> None:
    run.progress(1, "Intake and eligibility check")
    clarified = bool(run.state.get("clarified"))
    res = guard.check_input(_brief_text(run), scope="brief", use_model=not clarified, run_id=run.id)
    log_action(
        run.id,
        "guard",
        "check_brief",
        model=llm.model_name() if res.layer == "model" else None,
        cost=0,
        verdict=res.verdict,
        rule=res.rule,
        layer=res.layer,
    )
    if res.verdict == "clarify" and not clarified:
        run.state["clarify"] = res.message
        emit(run.id, 1, "clarify", res.message)
        run.save(Stage.AWAIT_CLARIFY)
        return
    if res.blocked:
        _stop(run, res)
        return
    brief = intake.run(run.id, run.brief_raw["text"], run.brief_raw["fields"])
    run.state["brief"] = brief.model_dump()
    run.save(Stage.PHASE1)
