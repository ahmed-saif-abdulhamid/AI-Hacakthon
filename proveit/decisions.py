"""Founder decisions: what the founder may do at each stage, and applying their choice.

The console shows exactly ``allowed_decisions(run)`` as buttons; ``founder_decide`` refuses
anything else. ``on_approval_decided`` moves a run on once the founder has approved or
rejected the exact bytes of a gated action.
"""

from __future__ import annotations

import json

from . import approval, db, guard
from .commerce import refunds
from .log import log_action, utcnow
from .models import GateDecision
from .orchestrator import Run, load, say
from .reports import simple_gate_md

# ---- founder decisions ------------------------------------------------------------


def _evidence_choice_open(run: Run) -> bool:
    """After Gate 1 (evidence) and before Gate 2, the founder may search again, try another angle or
    override with a reason. Never after an eligibility STOP (excluded product categories)."""
    g1 = run.state.get("gate1") or {}
    return (
        run.stage in ("await_founder", "stopped")
        and g1.get("gate") == "gate1_evidence"
        and not run.state.get("gate2")
        and not run.state.get("override")
    )


def allowed_decisions(run: Run) -> list[str]:
    """What the founder can do right now; the console shows exactly these buttons."""
    out = []
    if run.stage == "await_clarify":
        out.append("clarify_ok")
    if _evidence_choice_open(run):
        out += ["repeat", "override"]
        if run.next_variant():
            out.append("pivot")
        if run.stage == "await_founder":
            out.append("stop")
    if run.stage == "await_override":
        out += ["override", "stop"]
    if run.stage == "await_gate4":
        out += ["gate4_approve", "gate4_reject"]
    return out


NOT_ALLOWED = {
    "override": "You can only carry on against the evidence at the first or second checkpoint, and never for "
    "a product type ProveIt can't build.",
    "repeat": "Searching again is only possible right after the first checkpoint.",
    "pivot": "There is no other angle left to try for this idea.",
}


def founder_decide(run_id: str, decision: str, reason: str = "") -> dict:
    """Founder buttons: accept | stop | override | pivot | repeat | clarify_ok | gate4_approve | gate4_reject."""
    run = load(run_id)
    if decision in ("override", "repeat", "pivot") and decision not in allowed_decisions(run):
        log_action(run.id, "orchestrator", "refuse_founder_decision", decision=decision, stage=run.stage)
        return {"ok": False, "error": NOT_ALLOWED[decision]}
    if decision == "clarify_ok" and run.stage == "await_clarify":
        log_action(run.id, "founder", "confirm_digital_product", approved_by="founder")
        run.state["clarified"] = True
        run.save("intake", status="running")
        return {"ok": True, "stage": "intake"}
    if decision == "override":
        if len(reason.strip()) < 8:
            return {"ok": False, "error": "Please write a short reason for carrying on; it is saved with the decision."}
        res = guard.check_input(reason, scope="override", use_model=True, run_id=run.id)
        if guard.UNAVAILABLE in (res.notes or []):  # fail closed: no unchecked override
            return {
                "ok": False,
                "error": "I couldn't run the safety check on your reason just now (the AI service "
                "is busy). Please press it again in a few seconds.",
            }
        if res.blocked:
            log_action(run.id, "guard", "block_override_reason", rule=res.rule)
            return {"ok": False, "error": res.message, "rule": res.rule}
        gate = "gate2" if run.stage == "await_override" else "gate1"
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
        fname = "phase2_gate_decision.md" if gate == "gate2" else "phase1_gate_decision.md"
        if (run.dir / fname).exists():
            txt = (run.dir / fname).read_text(encoding="utf-8")
            txt = txt.replace(
                "- **Founder decision:** pending",
                f"- **Founder decision:** overridden against the evidence (logged). Reason: {reason}",
                1,
            )
            run.write(fname, txt)
        key = "gate2" if gate == "gate2" else "gate1"
        if key in run.state:
            run.state[key]["founder_decision"] = "overridden"
            run.state[key]["override_reason"] = reason
        say(run, "override")
        run.save("phase3" if gate == "gate2" else "phase2", status="running")
        db.execute("UPDATE runs SET override_reason=? WHERE id=?", (reason, run.id))
        return {"ok": True, "stage": run.stage}
    if decision in ("gate4_approve", "gate4_reject") and run.stage == "await_gate4":
        ok = decision == "gate4_approve"
        log_action(run.id, "founder", "gate4_approve" if ok else "gate4_reject", approved_by="founder" if ok else None)
        dec = GateDecision(
            run_id=run.id,
            gate="gate4_commercial",
            outcome="go" if ok else "stop",
            reason="founder_approved_pricing_and_policies" if ok else "founder_rejected",
            thresholds={"founder_approval": True},
            thresholds_sha256=run.sha,
            rule_fired="g4_founder",
            founder_decision="accepted" if ok else "stopped",
            recommendation="Founder approved the price and the policy drafts."
            if ok
            else "Founder rejected; revise pricing or policies.",
        )
        run.write(
            "phase4_gate_decision.md", simple_gate_md("Phase 4 gate: founder approval of price and policies", dec)
        )
        run.state["gate4"] = dec.model_dump()
        rejects = run.state.setdefault("rejections", {})
        rejects["gate4"] = rejects.get("gate4", 0) + (0 if ok else 1)
        redo = not ok and rejects["gate4"] <= 2
        if redo:
            log_action(run.id, "orchestrator", "redo_phase4_after_founder_rejection")
        run.save("phase5" if ok else ("phase4" if redo else "stopped"), status="running" if ok or redo else "stopped")
        return {"ok": True, "stage": run.stage}
    if decision == "pivot":
        n = run.next_variant()
        if n is None:
            return {"ok": False, "error": "Every angle has already been researched."}
        log_action(run.id, "founder", f"pivot_to_variant_{n}", approved_by="founder")
        old = run.dir / "phase1_gate_decision.md"  # keep the verdict on the angle left behind
        if old.exists():
            old.replace(run.dir / f"phase1_gate_variant-{run.state.get('variant_n', 1)}.md")
        run.state["variant_n"] = n
        run.save("phase1", status="running")
        return {"ok": True, "stage": "phase1"}
    if decision == "repeat":
        log_action(run.id, "founder", "repeat_research", approved_by="founder")
        run.state["repeats"] = run.state.get("repeats", 0) + 1
        run.save("phase1", status="running")
        return {"ok": True, "stage": "phase1"}
    if decision in ("accept", "stop") and run.stage not in ("await_founder", "await_override", "await_clarify"):
        return {"ok": False, "error": "There's nothing to decide at this step."}
    if decision in ("accept", "stop"):
        gate_key = "gate2" if run.stage == "await_override" else "gate1"
        log_action(
            run.id,
            "founder",
            f"accept_{gate_key}_recommendation" if decision == "accept" else "stop_run",
            approved_by="founder",
        )
        if gate_key in run.state:
            run.state[gate_key]["founder_decision"] = "accepted" if decision == "accept" else "stopped"
        run.save("stopped", status="stopped")
        return {"ok": True, "stage": "stopped"}
    return {"ok": False, "error": "That choice isn't available at this step."}


# ---- approvals ----------------------------------------------------------------


def on_approval_decided(approval_id: str) -> str | None:
    """Called after the founder clicks approve/reject. Executes the gated action with the stored bytes."""
    ap = approval.load(approval_id)
    if ap is None:
        return None
    try:
        run = load(ap.run_id)
        pending = run.state.get("pending_approval") or {}
    except KeyError:
        run, pending = None, {}
    if pending.get("id") != approval_id:
        # A refund a customer asked for from the store page is not a pipeline step: run it whenever the
        # founder approves it (or just log the rejection), whatever stage the run is at.
        if ap.action == "refund":
            order_id = json.loads(approval.blob(ap.payload_sha256)[0]).get("order_id")
            if ap.status == "approved":
                refunds.refund(order_id, approval_id)
                log_action(
                    ap.run_id,
                    "orchestrator",
                    "customer_refund_executed",
                    order_id=order_id,
                    approved_by="founder",
                    test=True,
                )
            else:
                log_action(ap.run_id, "orchestrator", "customer_refund_rejected", order_id=order_id)
        return run.stage if run else None
    payload, _ = approval.blob(ap.payload_sha256)
    run.state.pop("pending_approval", None)
    if ap.status == "rejected":
        redo = {"publish_landing_page": "phase2", "open_store": "phase5"}.get(ap.action)
        rejects = run.state.setdefault("rejections", {})
        rejects[ap.action] = rejects.get(ap.action, 0) + 1
        if redo and rejects[ap.action] <= 2:
            log_action(run.id, "orchestrator", f"regenerate_after_rejected_{ap.action}")
            run.save(redo, status="running")
            return redo
        if ap.action == "refund":
            log_action(run.id, "orchestrator", "refund_not_executed_founder_rejected")
            run.save("phase6", status="running")
            return "phase6"
        log_action(run.id, "orchestrator", f"founder_rejected_{ap.action}")
        run.save("stopped", status="stopped")
        return "stopped"
    say(run, "approved", action=ap.action)
    if ap.action == "publish_landing_page":
        approval.publish_landing_page(payload, approval_id, run_id=run.id)
        run.save("gate2", status="running")
    elif ap.action == "open_store":
        approval.open_store(payload, approval_id, run_id=run.id)
        run.save("payment_test", status="running")
    elif ap.action == "refund":
        run.state["refund_approval"] = approval_id
        run.save("refund", status="running")
    return run.stage
