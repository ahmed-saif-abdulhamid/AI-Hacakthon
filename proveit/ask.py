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

APP_FACTS = (
    "ProveIt runs six phases: 1 Discover (find real complaints on Hacker News, Stack Exchange, GitHub, "
    "Wikipedia and optional web search, cut verbatim quotes and re-check them on the live page), 2 Validate "
    "(Lean Canvas and a waitlist landing page), 3 Build (a downloadable toolkit of templates and guides), "
    "4 Commercial setup (prices from verified price points, refund and privacy policy drafts), 5 Sell, "
    "deliver and get paid (MOCKED payment, delivery link, refund revokes access), 6 Operate and learn (STUBBED). "
    "Gates between phases decide go, repeat, pivot or stop using rules written in code, with thresholds "
    "locked by a SHA-256 hash before any search. The founder can accept, repeat, pivot, stop, or override "
    "with a logged reason. Nothing is published without the founder pressing the hash-locked Approve button. "
    "The model is NVIDIA Nemotron on NVIDIA's free hosted API; a run costs $0.00. To start a run, fill in the idea in the "
    "brief form or say: evaluate this idea, followed by the idea."
)


def run_context(run) -> str:
    """A compact, factual summary of one run for the assistant (no invented fields)."""
    if run is None:
        return "No run is selected."
    s = run.state
    brief = s.get("brief") or {}
    out = [f"Run {run.id} ({run.label or 'no label'}), stage {run.stage}, phase {s.get('phase', 1)} of 6.",
           "Idea: " + str(brief.get("idea") or (run.brief_raw or {}).get("fields", {}).get("idea")
                          or (run.brief_raw or {}).get("text", ""))[:300]]
    variants = s.get("variants") or []
    if variants:
        v = variants[min(len(variants), s.get("variant_n", 1)) - 1]
        out.append(f"Variant researched: {v.get('title')} for {v.get('segment')}; job: {v.get('job_to_be_done')}.")
    for name in ("gate1", "gate2", "gate3", "gate4"):
        g = s.get(name)
        if not g:
            continue
        line = (f"{name.upper()}: outcome {str(g.get('outcome', '')).upper()}, reason {g.get('reason')}, "
                f"rule {g.get('rule_fired')}, founder decision {g.get('founder_decision')}. "
                f"{g.get('recommendation', '')}")
        m, t = g.get("metrics") or {}, g.get("thresholds") or {}
        if m and t:
            line += (f" Weighted pain signals {m.get('sourced_pain')} (needs {t.get('min_sourced_pain')}); coverage "
                     f"{m.get('coverage')} (needs {t.get('min_coverage')}); distinct sources "
                     f"{m.get('distinct_sources')}; payment signals {m.get('wtp_signals')}; "
                     f"competitors {m.get('competitors')}.")
        out.append(line)
    if s.get("override"):
        out.append(f"The founder overrode the evidence: {str(s['override'].get('reason', ''))[:200]}. "
                   "Later phases are a preview.")
    counted = sorted([c for c in run.claims() if c.weight > 0], key=lambda c: -c.weight)[:4]
    for c in counted:
        out.append(f"Evidence {c.id} ({c.kind}, weight {c.weight}, {c.source}): \"{(c.quote or '')[:180]}\"")
    if not counted and s.get("claims"):
        out.append("No quote passed the relevance and cue checks with a weight above zero.")
    if s.get("debate"):
        adv = " ".join(x.get("text", "") for x in s["debate"].get("advocate", [])[:2])
        skp = " ".join(x.get("text", "") for x in s["debate"].get("skeptic", [])[:2])
        out.append(f"Advocate: {adv[:300]} Skeptic: {skp[:300]}")
    pend = approval.list_approvals(run.id, "pending")
    if pend:
        out.append("Pending approvals: " + ", ".join(a.action for a in pend) + ".")
    try:
        files = sorted(p.name for p in run.dir.iterdir() if p.name.startswith(("phase", "payment")))
    except (OSError, AttributeError):
        files = []
    if files:
        out.append("Files produced: " + ", ".join(files[:30]) + ".")
    if s.get("error"):
        out.append(f"Last error: {str(s['error'])[:200]}")
    return "\n".join(out)


def strip_wake(text: str) -> str:
    """Drop a leading wake word ("Jarvis", "hey Jarvis") from a spoken or typed request."""
    return re.sub(r"^\s*(hey|ok|okay)?[\s,]*jarvis\b[\s,.:!?-]*", "", text or "", flags=re.I).strip()


SENTENCE_END = re.compile(r"(?<=[.!?])\s+(?=[A-Z0-9\"'(])")


def _messages(text: str, history: list[dict] | None) -> list[dict]:
    msgs = []
    for h in (history or [])[-6:]:
        role = "user" if h.get("role") == "user" else "assistant"
        msgs.append({"role": role, "content": str(h.get("text", ""))[:400]})
    msgs.append({"role": "user", "content": text[:600]})
    return msgs


def _system(run) -> str:
    """System prompt for the assistant. Identical across turns of one run, so the model caches it."""
    return (llm.fill(llm.load_prompt("assistant"), address=voice.address())
            + f"\n\nAPP FACTS:\n{APP_FACTS}\n\nRUN CONTEXT:\n{run_context(run)}")


def converse_stream(text: str, run, history: list[dict] | None = None):
    """Grounded free-form answer from the local model, yielded one checked sentence at a time.

    Each sentence passes rule set C (minus money words) before it is yielded, so nothing is
    spoken that the guard would block. Raises llm.LLMError when the model is unavailable.
    """
    system = _system(run)
    rid = run.id if run else None
    t0, buf, said = __import__("time").time(), "", []

    def clean(s: str) -> str | None:
        s = re.sub(r"[*#`]+", "", s).replace("_", " ").strip()
        if not s:
            return None
        if guard.check_output(s, "policy").blocked:
            log_action(rid, "guard", "assistant_sentence_blocked", model=None, cost=0)
            return None
        said.append(s)
        return s

    try:
        for chunk in llm.chat_stream(system, _messages(text, history), run_id=rid, num_predict=200):
            buf += chunk
            parts = SENTENCE_END.split(buf)
            for done in parts[:-1]:
                s = clean(done)
                if s:
                    yield s
            buf = parts[-1]
        s = clean(buf)
        if s:
            yield s
    except llm.LLMError as e:
        log_action(rid, "assistant", "answer_failed", model=llm.model_name(), cost=0, error=str(e)[:120])
        if not said:
            raise
    log_action(rid, "assistant", "answer_question", model=llm.model_name(), cost=0,
               seconds=round(__import__("time").time() - t0, 2), sentences=len(said))


def warm(run) -> None:
    """Pre-read one run's context into the model's cache so the first spoken answer starts quickly."""
    system = _system(run)
    try:
        for _ in llm.chat_stream(system, [{"role": "user", "content": "Ready?"}], num_predict=1):
            pass
    except llm.LLMError:
        pass


def offline_answer(text: str, run) -> str:
    """Answer from the recorded run without a model (public demo, or the NVIDIA API not answering)."""
    import os
    s = voice.address()
    tail = (" This hosted demo has no model attached, so I answer from the recorded run; run ProveIt locally "
            "for full conversation." if os.environ.get("PROVEIT_DEMO") == "1"
            else " The NVIDIA model is not answering; check NVIDIA_API_KEY in .env and your connection.")
    if run is None or not run.state.get("gate1"):
        return f"Select a run and I will tell you what the evidence says, {s}." + tail
    g = run.state["gate1"]
    t = (text or "").lower()
    if re.search(r"quote|evidence|found|said|say|complain|source|people", t):
        top = sorted([c for c in run.claims() if c.weight > 0], key=lambda c: -c.weight)[:2]
        if top:
            quotes = " ".join(f"On {c.source}, someone wrote: {(c.quote or '')[:160]}" for c in top)
            return f"{len(top)} of the strongest counted quotes, {s}. {quotes}" + tail
        return "No quote passed the relevance and wording checks, " + s + "." + tail
    if re.search(r"next|should|do now|recommend|continue|give up", t):
        return voice.gate_line(**g) + " The decision is yours: accept, search again, pivot or stop." + tail
    return voice.gate_line(**g) + tail


def converse(text: str, run, history: list[dict] | None = None, use_model: bool = True) -> str | None:
    """The whole answer as one string. None when the model is unavailable or said nothing."""
    if not use_model:
        return None
    try:
        out = " ".join(converse_stream(text, run, history))
    except llm.LLMError:
        return None
    return out or None


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


def handle(text: str, run_id: str | None = None, use_model: bool = True,
           history: list[dict] | None = None, stream: bool = False) -> dict:
    from . import orchestrator
    text = strip_wake(text)
    if not text:
        return {"intent": "wake", "text": "Listening.", "spoken": "Yes, " + voice.address() + "?", "listen": True}
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
        if stream and use_model:
            return {"intent": intent, "converse": True, "text": out["text"], "fallback": out["spoken"]}
        spoken = converse(text, run, history, use_model)
        return {"intent": intent, "text": (spoken + "\n\n" if spoken else "") + out["text"],
                "spoken": spoken or out["spoken"]}
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
        idea = brief[-1].strip() if len(brief) > 1 else re.sub(
            r"(?i)^.*?\b(idea|brief|concept)\b[\s,:.-]*(is|of)?\s*", "", text).strip()
        if len(idea) < 8:
            return {"intent": intent, "text": "Tell me the idea in one sentence, for example: evaluate this idea: "
                    "a contract template pack for freelance photographers.",
                    "spoken": "Certainly, " + voice.address() + ". What is the idea?"}
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
    if stream and use_model:
        return {"intent": "other", "converse": True, "text": ""}
    spoken = converse(text, run, history, use_model)
    if spoken:
        return {"intent": "other", "text": spoken, "spoken": spoken}
    msg = offline_answer(text, run)
    return {"intent": "other", "text": msg, "spoken": msg}
