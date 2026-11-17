"""Founder decisions: what the founder may do at each stage, and applying their choice.

The console shows exactly ``allowed_decisions(run)`` as buttons; ``founder_decide`` refuses
anything else. ``on_approval_decided`` moves a run on once the founder has approved or
rejected the exact bytes of a gated action.
"""

from __future__ import annotations

import json
from collections.abc import Callable

from . import approval, db, guard
from .commerce import refunds
from .log import log_action, utcnow
from .models import Approval, GateDecision
from .pipeline.run import Run, Stage, Status, load
from .reports.common import simple_gate_md

MIN_OVERRIDE_REASON_CHARS = 8
MAX_REDRAFTS = 2  # a rejected landing page, store page or Gate 4 is redrafted at most twice
GATE_FILES = {"gate1": "phase1_gate_decision.md", "gate2": "phase2_gate_decision.md"}

NOT_ALLOWED = {
    "override": "You can only carry on against the evidence at the first or second checkpoint, and never for "
    "a product type ProveIt can't build.",
    "repeat": "Searching again is only possible right after the first checkpoint.",
    "pivot": "There is no other angle left to try for this idea.",
}
UNAVAILABLE = "That choice isn't available at this step."
NOTHING_TO_DECIDE = "There's nothing to decide at this step."

Result = dict


def _ok(stage: str) -> Result:
    return {"ok": True, "stage": stage}


def _refused(error: str, **extra) -> Result:
    return {"ok": False, "error": error, **extra}


# ---- what the founder may do ---------------------------------------------------------------


def _evidence_choice_open(run: Run) -> bool:
    """After Gate 1 (evidence) and before Gate 2, the founder may search again, try another angle or
    override with a reason. Never after an eligibility STOP (excluded product categories)."""
    g1 = run.state.get("gate1") or {}
    return (
        run.stage in (Stage.AWAIT_FOUNDER, Stage.STOPPED)
        and g1.get("gate") == "gate1_evidence"
        and not run.state.get("gate2")
        and not run.state.get("override")
    )


def allowed_decisions(run: Run) -> list[str]:
    """What the founder can do right now; the console shows exactly these buttons."""
    out = []
    if run.stage == Stage.AWAIT_CLARIFY:
        out.append("clarify_ok")
    if _evidence_choice_open(run):
        out += ["repeat", "override"]
        if run.next_variant():
            out.append("pivot")
        if run.stage == Stage.AWAIT_FOUNDER:
            out.append("stop")
    if run.stage == Stage.AWAIT_OVERRIDE:
        out += ["override", "stop"]
    if run.stage == Stage.AWAIT_GATE4:
        out += ["gate4_approve", "gate4_reject"]
    return out


# ---- one handler per decision -----------------------------------------------------------------


def _clarify_ok(run: Run, reason: str) -> Result:
    log_action(run.id, "founder", "confirm_digital_product", approved_by="founder")
    run.state["clarified"] = True
    run.save(Stage.INTAKE, status=Status.RUNNING)
    return _ok(Stage.INTAKE)


def _mark_gate_file_overridden(run: Run, gate: str, reason: str) -> None:
    text = run.read(GATE_FILES[gate])
    if text:
        run.write(
            GATE_FILES[gate],
            text.replace(
                "- **Founder decision:** pending",
                f"- **Founder decision:** overridden against the evidence (logged). Reason: {reason}",
                1,
            ),
        )


def _override(run: Run, reason: str) -> Result:
    if len(reason.strip()) < MIN_OVERRIDE_REASON_CHARS:
        return _refused("Please write a short reason for carrying on; it is saved with the decision.")
    res = guard.check_input(reason, scope="override", use_model=True, run_id=run.id)
    if guard.UNAVAILABLE in (res.notes or []):  # fail closed: no unchecked override
        return _refused(
            "I couldn't run the safety check on your reason just now (the AI service "
            "is busy). Please press it again in a few seconds."
        )
    if res.blocked:
        log_action(run.id, "guard", "block_override_reason", rule=res.rule)
        return _refused(res.message, rule=res.rule)
    gate = "gate2" if run.stage == Stage.AWAIT_OVERRIDE else "gate1"
    log_action(
        run.id,
        "founder",
        "founder_override_against_evidence",
        approved_by="founder",
        gate=gate,
        override_reason=reason,
    )
    run.state["override"] = {"gate": gate, "reason": reason, "at": utcnow()}
    run.state.setdefault("overrides", []).append(gate)
    _mark_gate_file_overridden(run, gate, reason)
    if gate in run.state:
        run.state[gate]["founder_decision"] = "overridden"
        run.state[gate]["override_reason"] = reason
    run.say("override")
    run.save(Stage.PHASE3 if gate == "gate2" else Stage.PHASE2, status=Status.RUNNING)
    db.execute("UPDATE runs SET override_reason=? WHERE id=?", (reason, run.id))
    return _ok(run.stage)


def _count_rejection(run: Run, key: str) -> int:
    rejects = run.state.setdefault("rejections", {})
    rejects[key] = rejects.get(key, 0) + 1
    return rejects[key]


def _gate4(run: Run, approved: bool) -> Result:
    log_action(
        run.id, "founder", "gate4_approve" if approved else "gate4_reject", approved_by="founder" if approved else None
    )
    dec = GateDecision(
        run_id=run.id,
        gate="gate4_commercial",
        outcome="go" if approved else "stop",
        reason="founder_approved_pricing_and_policies" if approved else "founder_rejected",
        thresholds={"founder_approval": True},
        thresholds_sha256=run.sha,
        rule_fired="g4_founder",
        founder_decision="accepted" if approved else "stopped",
        recommendation="Founder approved the price and the policy drafts."
        if approved
        else "Founder rejected; revise pricing or policies.",
    )
    run.write("phase4_gate_decision.md", simple_gate_md("Phase 4 gate: founder approval of price and policies", dec))
    run.state["gate4"] = dec.model_dump()
    if approved:
        run.save(Stage.PHASE5, status=Status.RUNNING)
    elif _count_rejection(run, "gate4") <= MAX_REDRAFTS:
        log_action(run.id, "orchestrator", "redo_phase4_after_founder_rejection")
        run.save(Stage.PHASE4, status=Status.RUNNING)
    else:
        run.save(Stage.STOPPED, status=Status.STOPPED)
    return _ok(run.stage)


def _pivot(run: Run, reason: str) -> Result:
    n = run.next_variant()
    if n is None:
        return _refused("Every angle has already been researched.")
    log_action(run.id, "founder", f"pivot_to_variant_{n}", approved_by="founder")
    old = run.dir / GATE_FILES["gate1"]  # keep the verdict on the angle left behind
    if old.exists():
        old.replace(run.dir / f"phase1_gate_variant-{run.state.get('variant_n', 1)}.md")
    run.state["variant_n"] = n
    run.save(Stage.PHASE1, status=Status.RUNNING)
    return _ok(Stage.PHASE1)


def _repeat(run: Run, reason: str) -> Result:
    log_action(run.id, "founder", "repeat_research", approved_by="founder")
    run.state["repeats"] = run.state.get("repeats", 0) + 1
    run.save(Stage.PHASE1, status=Status.RUNNING)
    return _ok(Stage.PHASE1)


def _accept_or_stop(run: Run, accept: bool) -> Result:
    gate = "gate2" if run.stage == Stage.AWAIT_OVERRIDE else "gate1"
    log_action(run.id, "founder", f"accept_{gate}_recommendation" if accept else "stop_run", approved_by="founder")
    if gate in run.state:
        run.state[gate]["founder_decision"] = "accepted" if accept else "stopped"
    run.save(Stage.STOPPED, status=Status.STOPPED)
    return _ok(Stage.STOPPED)


DECISIONS: dict[str, Callable[[Run, str], Result]] = {
    "clarify_ok": _clarify_ok,
    "override": _override,
    "gate4_approve": lambda run, reason: _gate4(run, approved=True),
    "gate4_reject": lambda run, reason: _gate4(run, approved=False),
    "pivot": _pivot,
    "repeat": _repeat,
    "accept": lambda run, reason: _accept_or_stop(run, accept=True),
    "stop": lambda run, reason: _accept_or_stop(run, accept=False),
}
# Stage preconditions, and the message when the run is elsewhere.
REQUIRED_STAGES: dict[str, tuple[frozenset[str], str]] = {
    "clarify_ok": (frozenset({Stage.AWAIT_CLARIFY}), UNAVAILABLE),
    "gate4_approve": (frozenset({Stage.AWAIT_GATE4}), UNAVAILABLE),
    "gate4_reject": (frozenset({Stage.AWAIT_GATE4}), UNAVAILABLE),
    "accept": (frozenset({Stage.AWAIT_FOUNDER, Stage.AWAIT_OVERRIDE, Stage.AWAIT_CLARIFY}), NOTHING_TO_DECIDE),
    "stop": (frozenset({Stage.AWAIT_FOUNDER, Stage.AWAIT_OVERRIDE, Stage.AWAIT_CLARIFY}), NOTHING_TO_DECIDE),
}


def founder_decide(run_id: str, decision: str, reason: str = "") -> Result:
    """Founder buttons: accept | stop | override | pivot | repeat | clarify_ok | gate4_approve | gate4_reject."""
    run = load(run_id)
    handler = DECISIONS.get(decision)
    if handler is None:
        return _refused(UNAVAILABLE)
    if decision in NOT_ALLOWED and decision not in allowed_decisions(run):
        log_action(run.id, "orchestrator", "refuse_founder_decision", decision=decision, stage=run.stage)
        return _refused(NOT_ALLOWED[decision])
    stages, wrong_stage_message = REQUIRED_STAGES.get(decision, (None, ""))
    if stages is not None and run.stage not in stages:
        return _refused(wrong_stage_message)
    return handler(run, reason)


# ---- approvals ----------------------------------------------------------------

REDRAFT_STAGE = {"publish_landing_page": Stage.PHASE2, "open_store": Stage.PHASE5}


def _customer_refund(ap: Approval) -> None:
    """A refund a customer asked for from the store page is not a pipeline step: run it whenever the
    founder approves it (or just log the rejection), whatever stage the run is at."""
    order_id = json.loads(approval.blob(ap.payload_sha256)[0]).get("order_id")
    if ap.status == "approved":
        refunds.refund(order_id, ap.id)
        log_action(
            ap.run_id, "orchestrator", "customer_refund_executed", order_id=order_id, approved_by="founder", test=True
        )
    else:
        log_action(ap.run_id, "orchestrator", "customer_refund_rejected", order_id=order_id)


def _on_rejected(run: Run, ap: Approval) -> str:
    redo = REDRAFT_STAGE.get(ap.action)
    if redo and _count_rejection(run, ap.action) <= MAX_REDRAFTS:
        log_action(run.id, "orchestrator", f"regenerate_after_rejected_{ap.action}")
        run.save(redo, status=Status.RUNNING)
    elif ap.action == "refund":
        log_action(run.id, "orchestrator", "refund_not_executed_founder_rejected")
        run.save(Stage.PHASE6, status=Status.RUNNING)
    else:
        log_action(run.id, "orchestrator", f"founder_rejected_{ap.action}")
        run.save(Stage.STOPPED, status=Status.STOPPED)
    return run.stage


def _on_approved(run: Run, ap: Approval) -> str:
    run.say("approved", action=ap.action)
    payload, _ = approval.blob(ap.payload_sha256)
    if ap.action == "publish_landing_page":
        approval.publish_landing_page(payload, ap.id, run_id=run.id)
        run.save(Stage.GATE2, status=Status.RUNNING)
    elif ap.action == "open_store":
        approval.open_store(payload, ap.id, run_id=run.id)
        run.save(Stage.PAYMENT_TEST, status=Status.RUNNING)
    elif ap.action == "refund":
        run.state["refund_approval"] = ap.id
        run.save(Stage.REFUND, status=Status.RUNNING)
    return run.stage


def on_approval_decided(approval_id: str) -> str | None:
    """Called after the founder clicks approve/reject. Executes the gated action with the stored bytes."""
    ap = approval.load(approval_id)
    if ap is None:
        return None
    try:
        run = load(ap.run_id)
    except KeyError:
        run = None
    pending = (run.state.get("pending_approval") or {}) if run else {}
    if pending.get("id") != approval_id:
        if ap.action == "refund":
            _customer_refund(ap)
        return run.stage if run else None
    run.state.pop("pending_approval", None)
    return _on_rejected(run, ap) if ap.status == "rejected" else _on_approved(run, ap)
