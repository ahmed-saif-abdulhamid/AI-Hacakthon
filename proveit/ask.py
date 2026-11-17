"""Ask J.A.R.V.I.S.: the command bar on every screen (typed or spoken).

Text goes through guard rule set A (and the model check) first. Rule hits are refused
before any generating model sees the text. Then a fixed router picks one intent:
edit_copy, explain_decision, rerun_step, change_threshold, approve_request, evaluate_brief, other.
A message is never an approval: approvals come only from the hash-bound buttons or the CLI.
"""
from __future__ import annotations

import re

from . import approval, guard, llm, voice
from .log import emit, log_action


def _gate_summary(run) -> dict:
    g = run.state.get("gate1")
    if not g:
        return {"text": "No gate decision exists yet for this run.", "spoken": "There is no gate decision yet, "
                + voice.address() + "."}
    m, t = g.get("metrics", {}), g.get("thresholds", {})
    lines = [f"Gate 1 outcome: {g['outcome'].upper()} ({g['reason']}, {g['rule_fired']}).",
             g.get("recommendation", "")]
    if m:
        lines.append(f"Weighted pain signals {m.get('sourced_pain')} vs threshold {t.get('min_sourced_pain')}; "
                     f"coverage {m.get('coverage')} vs {t.get('min_coverage')}; distinct sources "
                     f"{m.get('distinct_sources')}; payment signals {m.get('wtp_signals')}; "
                     f"competitors {m.get('competitors')}; founder fit {m.get('founder_fit')}.")
    counted = sorted([c for c in run.claims() if c.weight > 0], key=lambda c: -c.weight)[:3]
    for c in counted:
        lines.append(f"[{c.id}] \"{(c.quote or '')[:160]}\" ({c.url}, {c.status}, weight {c.weight})")
    if not counted:
        lines.append("No claim passed the code relevance and cue check with a weight above zero.")
    lines.append(f"Thresholds SHA-256: {g.get('thresholds_sha256', '')[:16]}... goalpost_moved="
                 f"{str(g.get('goalpost_moved')).lower()}")
    return {"text": "\n".join(lines), "spoken": voice.gate_line(**g)}


def handle(text: str, run_id: str | None = None, use_model: bool = True) -> dict:
    from . import orchestrator
    res = guard.check_input(text, scope="ask", use_model=use_model, run_id=run_id)
    if res.blocked:
        log_action(run_id, "guard", "refuse_ask_request", model=llm.model_name() if res.layer == "model" else None,
                   cost=0, rule=res.rule, layer=res.layer)
        spoken = voice.refusal_line(res.rule or "", res.message, res.notes)
        if run_id:
            emit(run_id, 0, "protocol0", spoken, rule=res.rule)
        return {"intent": "refused", "refused": True, "rule": res.rule, "layer": res.layer, "text": res.message,
                "spoken": spoken, "alert": "crimson"}
    intent = guard.route_intent(text)
    run = None
    if run_id:
        try:
            run = orchestrator.load(run_id)
        except KeyError:
            run = None
    log_action(run_id, "ask", f"ask_{intent}", model=None, cost=0)
    if intent == "explain_decision":
        if run is None:
            return {"intent": intent, "text": "Select a run first.", "spoken": "Which run, " + voice.address() + "?"}
        out = _gate_summary(run)
        return {"intent": intent, **out}
    if intent == "change_threshold":
        sha = run.sha[:12] if run else ""
        msg = (f"Thresholds were pre-registered before any data was seen (SHA-256 {sha}...). Changing one now is "
               "logged as goalpost_moved: true and shown in red. Edit config/gates.yaml before starting a new run.")
        return {"intent": intent, "text": msg, "spoken": "The thresholds are locked for this run, " + voice.address()
                + ". Any change would be logged as a moved goalpost."}
    if intent == "approve_request":
        pending = approval.list_approvals(run_id, "pending") if run_id else approval.list_approvals(status="pending")
        if not pending:
            return {"intent": intent, "text": "No approval is pending.", "spoken": "Nothing awaits approval, "
                    + voice.address() + "."}
        ap = pending[-1]
        return {"intent": intent, "highlight_approval": ap.id,
                "text": f"Pending: {ap.action} ({ap.id}), payload SHA-256 {ap.payload_sha256}. A message is not an "
                        "approval: use the hash-locked APPROVE button or `python -m proveit approvals approve "
                        f"{ap.id}`.",
                "spoken": f"The {ap.action.replace('_', ' ')} card is highlighted, {voice.address()}. "
                          "Please confirm with the hash-locked button."}
    if intent == "rerun_step":
        return {"intent": intent, "text": "Use the Repeat or Research-variant button at the gate; a rerun is logged.",
                "spoken": "Use the repeat control at the gate, " + voice.address() + ". Every rerun is logged."}
    if intent == "evaluate_brief":
        brief = re.split(r"(?i)\b(brief|idea)\s*:", text, maxsplit=1)
        idea = brief[-1].strip() if len(brief) > 1 else re.sub(r"(?i)^.*?\b(evaluate|assess|validate|check)\b\s*(this|my|the|a)?\s*", "", text)
        new_id = orchestrator.start(f"Idea: {idea}", mode="live", label="ask")
        return {"intent": intent, "run_id": new_id, "text": f"Started run {new_id}.",
                "spoken": "Right away, " + voice.address() + ". Evaluating the brief now.", "start_run": new_id}
    if intent == "edit_copy":
        if run is None or "variants" not in run.state:
            return {"intent": intent, "text": "Select a run that has landing copy first.", "spoken": "Which run, "
                    + voice.address() + "?"}
        from agents import strategist
        out = strategist.landing(run.id, run.variant(), feedback="Founder request: " + text[:300])
        copy = "\n".join([out.headline, out.subheadline] + out.benefits)
        chk = guard.check_output(copy, "outward", use_model=use_model, run_id=run.id)
        if chk.blocked:
            return {"intent": intent, "refused": True, "text": chk.message, "spoken": voice.refusal_line(chk.rule or "", chk.message),
                    "alert": "crimson"}
        return {"intent": intent, "text": "Suggested copy (not applied; it needs a new approval):\n" + copy,
                "spoken": "I have drafted revised copy for your review, " + voice.address() + "."}
    return {"intent": "other", "text": ("I can explain a decision, suggest copy edits, show pending approvals, or "
                                        "evaluate a new brief."),
            "spoken": "How may I help, " + voice.address() + "?"}
