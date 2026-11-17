"""Ask the assistant: the command bar on every screen (typed or spoken).

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
    "ProveIt checks whether people really want a digital product before the founder builds it. Step 1: it "
    "searches public forums (Hacker News, Stack Exchange, GitHub) for people describing the problem and checks "
    "every quote is really on that page. Step 2: a one-page business plan and a waiting-list page. Step 3: it "
    "builds the product files (templates, checklists, guides). Step 4: suggested prices and draft refund and "
    "privacy policies. Step 5: a practice sale, delivery and refund with no real money. Step 6: learning from "
    "results (not switched on yet). After each step there is a checkpoint that says go ahead, look again, try a "
    "different angle, or stop. The bar each checkpoint uses is set before any searching, so it can't be moved "
    "later. The founder can accept the advice, search again, try another angle, stop, or carry on anyway with a "
    "reason. Nothing is published or sent until the founder presses Approve. The AI runs on NVIDIA's free "
    "service, so a run costs nothing. To test a new idea, press Test a new idea, or say: evaluate this idea, "
    "followed by the idea."
)


def current_claims(run) -> list:
    """Claims of the variant currently on screen, with the persisted IDs the console and files show."""
    s = run.state
    hits = (s.get("research", {}).get(str(s.get("variant_n", 1)), {}) or {}).get("hits", {})
    claims = run.claims()
    return [c for c in claims if c.hit_id in hits] if hits else claims


def run_context(run) -> str:
    """A compact, factual summary of one run for the assistant (no invented fields)."""
    if run is None:
        return "No run is selected."
    s = run.state
    brief = s.get("brief") or {}
    out = [f"Run {run.id} ({run.label or 'no label'}), stage {run.stage}, phase {s.get('phase', 1)} of 6.",
           "Idea: " + str(brief.get("idea") or (run.brief_raw or {}).get("fields", {}).get("idea")
                          or (run.brief_raw or {}).get("text", ""))[:300]]
    known = {k: v for k, v in brief.items() if k in ("skills", "budget", "hours_per_week", "target_market", "values")
             and v and "unspecified" not in str(v).lower()}
    out.append("Founder (only these facts are known; the quotes are from strangers, never the founder): "
               + ("; ".join(f"{k.replace('_', ' ')}: {v}" for k, v in known.items()) or "nothing beyond the idea"))
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
    counted = sorted([c for c in current_claims(run) if c.weight > 0], key=lambda c: -c.weight)[:6]
    for c in counted:
        out.append(f"Evidence {c.id} ({c.kind}, weight {c.weight}, {c.source}): \"{(c.quote or '')[:180]}\"")
    if not counted and s.get("claims"):
        out.append("No quote passed the relevance and cue checks with a weight above zero.")
    if s.get("debate"):
        # Only arguments that cite a counted quote reach the assistant; uncited ones are opinions.
        ok = {c.id for c in current_claims(run) if c.weight > 0}
        def cited(side):
            return " ".join(x.get("text", "") for x in s["debate"].get(side, [])
                            if set(x.get("claim_ids") or []) & ok)[:300]
        adv, skp = cited("advocate"), cited("skeptic")
        if adv or skp:
            out.append(f"Cited arguments. For going ahead: {adv or 'none backed by a counted quote'}. "
                       f"For stopping: {skp or 'none backed by a counted quote'}.")
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
    """Drop a leading wake word (the assistant's name, "hey <name>") from a spoken or typed request."""
    name = re.escape(voice.assistant_name().lower())
    return re.sub(r"^\s*(hey|ok|okay)?[\s,]*" + name + r"\b[\s,.:!?-]*", "", text or "", flags=re.I).strip()


MAX_SENTENCES = 4
SENTENCE_END = re.compile(r"(?<=[.!?])\s+(?=[A-Z0-9\"'(])")


def _messages(text: str, history: list[dict] | None) -> list[dict]:
    msgs = []
    for h in (history or [])[-6:]:
        role = "user" if h.get("role") == "user" else "assistant"
        msgs.append({"role": role, "content": str(h.get("text", ""))[:400]})
    msgs.append({"role": "user", "content": text[:600]})
    return msgs


def _system(run, screen: list[str] | None = None) -> str:
    """System prompt for the assistant. Identical across turns of one run, so the model caches it."""
    shown = ("\n\nBUTTONS ON THE FOUNDER'S SCREEN RIGHT NOW: " + "; ".join(screen[:12])) if screen else ""
    return (llm.fill(llm.load_prompt("assistant"), address=voice.address() or "the founder",
                     name=voice.assistant_name())
            + f"\n\nAPP FACTS:\n{APP_FACTS}\n\nRUN CONTEXT:\n{run_context(run)}{shown}")


LIST_ITEM = re.compile(r"^\s*(\d+[.)]|first|second|third|fourth|fifth)\b", re.I)


def converse_stream(text: str, run, history: list[dict] | None = None, screen: list[str] | None = None):
    """Grounded free-form answer from the local model, yielded one checked sentence at a time.

    Each sentence passes rule set C (minus money words) before it is yielded, so nothing is
    spoken that the guard would block. Raises llm.LLMError when the model is unavailable.
    """
    system = _system(run, screen)
    rid = run.id if run else None
    t0, buf, said = __import__("time").time(), "", []
    dropped = []

    def clean(s: str) -> str | None:
        s = re.sub(r"[*#`]+", "", s).replace("_", " ").strip()
        if not s:
            return None
        if guard.check_output(s, "policy").blocked:
            log_action(rid, "guard", "assistant_sentence_blocked", model=None, cost=0)
            dropped.append(s)
            return None
        said.append(s)
        return s

    def full() -> bool:
        # A numbered list ("1. ... 2. ...") may finish its items; everything else stops at the cap.
        listing = sum(1 for x in said if LIST_ITEM.match(x))
        return len(said) >= MAX_SENTENCES + min(listing, 3)

    try:
        for chunk in llm.chat_stream(system, _messages(text, history), run_id=rid, num_predict=200):
            buf += chunk
            parts = SENTENCE_END.split(buf)
            for done in parts[:-1]:
                s = clean(done)
                if s:
                    yield s
                if full():                          # spoken answers stay short for a founder
                    buf = ""
                    break
            else:
                buf = parts[-1]
                continue
            break
        s = clean(buf) if not full() else None
        if s:
            yield s
        if dropped:                                     # never leave a silent gap in the answer
            note = "I left one point out because I couldn't put it without overstating the evidence."
            said.append(note)
            yield note
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
    tail = (" (This online demo can only read back the saved results.)" if os.environ.get("PROVEIT_DEMO") == "1"
            else " (I can't reach the AI service right now, so this is a short answer. Check the internet "
                 "connection and the NVIDIA key.)")
    if run is None or not run.state.get("gate1"):
        return f"Open one of your ideas on the left, {s}, and I'll tell you what I found." + tail
    g = run.state["gate1"]
    t = (text or "").lower()
    if re.search(r"quote|evidence|found|said|say|complain|source|people", t):
        top = sorted([c for c in run.claims() if c.weight > 0], key=lambda c: -c.weight)[:1]
        if top:
            return f"Here's one of the clearest comments I found, {s}: \"{(top[0].quote or '')[:160]}\"" + tail
        return f"I didn't find anyone clearly describing this problem, {s}." + tail
    if re.search(r"next|should|do now|recommend|continue|give up", t):
        return voice.gate_line(**g) + " It's your call, of course." + tail
    return voice.gate_line(**g) + tail


QUOTE_QUESTION = re.compile(r"\b(quotes?|what (did|do|does) (people|they|users|customers|anyone|folks) (say|said|write|wrote)|"
                            r"what are people saying|complain\w*|show me (the )?evidence|who (said|complained))\b", re.I)
KIND_WORDS = {"pain": "a complaint", "wtp": "someone saying they'd pay", "price_point": "a price",
              "competitor": "an existing tool"}


def quote_answer(run) -> dict:
    """Quotes are read back verbatim by code (with the IDs on screen), never paraphrased by the model."""
    counted = sorted([c for c in current_claims(run) if c.weight > 0], key=lambda c: (c.kind != "pain", -c.weight))
    pains = [c for c in counted if c.kind == "pain"]
    if not counted:
        msg = "I didn't find anyone clearly describing this problem in the places I searched."
        return {"intent": "quotes", "text": msg, "spoken": msg}
    pick = (pains or counted)[:2]
    places = {"hn": "Hacker News", "stackexchange": "Stack Exchange", "github": "GitHub", "web": "the web"}
    spoken = (f"I counted {len(pains)} {'complaint' if len(pains) == 1 else 'complaints'} about the problem. "
              if pains else "Nobody described the problem as a complaint, but here is what counted. ")
    spoken += " ".join(f"On {places.get(c.source, c.source)}, {KIND_WORDS.get(c.kind, 'someone')} "
                       f"({c.id}): \"{(c.quote or '')[:180]}\"" for c in pick)
    text = spoken + "\n\nAll counted quotes are in the Evidence tab, each linked to its source."
    return {"intent": "quotes", "text": text, "spoken": spoken}


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
           history: list[dict] | None = None, stream: bool = False, screen: list[str] | None = None) -> dict:
    res = _handle(text, run_id, use_model, history, stream, screen)
    for k in ("spoken", "text"):
        if isinstance(res.get(k), str):
            res[k] = voice.tidy(res[k]) if k == "spoken" else res[k]
    return res


def _handle(text: str, run_id: str | None, use_model: bool, history: list[dict] | None, stream: bool,
            screen: list[str] | None) -> dict:
    from . import orchestrator
    text = strip_wake(text)
    if not text:
        return {"intent": "wake", "text": "I'm listening.", "spoken": "Yes, " + voice.address() + "?", "listen": True}
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
    if QUOTE_QUESTION.search(text) and intent in ("explain_decision", "other"):
        intent = "quotes"
    run = None
    if run_id:
        try:
            run = orchestrator.load(run_id)
        except KeyError:
            run = None
    log_action(run_id, "ask", f"ask_{intent}", model=None, cost=0)
    if intent == "quotes":
        if run is None:
            return {"intent": intent, "text": "Open an idea on the left first.",
                    "spoken": "Which idea do you mean? Open it on the left and ask me again."}
        return quote_answer(run)
    if intent == "explain_decision":
        if run is None:
            return {"intent": intent, "text": "Open an idea on the left first.",
                    "spoken": "Which idea do you mean, " + voice.address() + "? Open it on the left and ask me again."}
        out = _gate_summary(run)
        if stream and use_model:
            return {"intent": intent, "converse": True, "text": out["text"], "fallback": out["spoken"]}
        spoken = converse(text, run, history, use_model)
        return {"intent": intent, "text": (spoken + "\n\n" if spoken else "") + out["text"],
                "spoken": spoken or out["spoken"]}
    if intent == "change_threshold":
        sha = run.sha[:12] if run else ""
        msg = ("The bar for this run was set before I looked at anything, so it stays as it is. That keeps the "
               "verdict honest. You can set a different bar for your next run (config/gates.yaml). "
               f"Fingerprint of this run's bar: {sha}...")
        return {"intent": intent, "text": msg, "spoken": "I'd rather not move the bar now that we've seen the "
                "results, " + voice.address() + ". It keeps the verdict honest. You can set a different one for "
                "your next idea."}
    if intent == "approve_request":
        pending = approval.list_approvals(run_id, "pending") if run_id else approval.list_approvals(status="pending")
        if not pending:
            return {"intent": intent, "text": "Nothing is waiting for your approval.",
                    "spoken": "There's nothing waiting for your approval right now, " + voice.address() + "."}
        ap = pending[-1]
        return {"intent": intent, "highlight_approval": ap.id,
                "text": f"The {ap.action.replace('_', ' ')} is waiting for you in the Approvals tab. Have a look, "
                        "then press Approve if you're happy. I can't approve things for you from a chat message.",
                "spoken": f"I've opened the {ap.action.replace('_', ' ')} for you, {voice.address()}. Have a look, "
                          "and press Approve if you're happy with it."}
    if intent == "rerun_step":
        return {"intent": intent, "text": "Press Search again (or Try another angle) under the verdict.",
                "spoken": "Sure. Just press Search again under the verdict, " + voice.address() + ", and I'll take "
                          "another look."}
    if intent == "evaluate_brief":
        brief = re.split(r"(?i)\b(brief|idea)\s*:", text, maxsplit=1)
        idea = brief[-1].strip() if len(brief) > 1 else re.sub(
            r"(?i)^.*?\b(idea|brief|concept)\b[\s,:.-]*(is|of)?\s*", "", text).strip()
        if len(idea) < 8:
            return {"intent": intent, "text": "Tell me the idea in one sentence, for example: evaluate this idea: "
                    "a contract template pack for freelance photographers.",
                    "spoken": "Happy to, " + voice.address() + ". What's the idea?"}
        new_id = orchestrator.start(f"Idea: {idea}", mode="live", label="ask")
        return {"intent": intent, "run_id": new_id, "text": "I've started looking into it.",
                "spoken": "Great, " + voice.address() + ". I'm looking into it now; it takes about a minute.",
                "start_run": new_id}
    if intent == "edit_copy":
        if run is None or "variants" not in run.state:
            return {"intent": intent, "text": "Open an idea that already has a landing page first.",
                    "spoken": "Which idea should I work on, " + voice.address() + "? Open it on the left first."}
        from agents import strategist
        out = strategist.landing(run.id, run.variant(), feedback="Founder request: " + text[:300])
        copy = "\n".join([out.headline, out.subheadline] + out.benefits)
        chk = guard.check_output(copy, "outward", use_model=use_model, run_id=run.id)
        if chk.blocked:
            return {"intent": intent, "refused": True, "text": chk.message, "spoken": voice.refusal_line(chk.rule or "", chk.message),
                    "alert": "crimson"}
        return {"intent": intent, "text": "Here's a new version (nothing changes until you approve it):\n" + copy,
                "spoken": "Here's a new version for you to look at, " + voice.address() + ". Nothing changes until "
                          "you approve it."}
    if stream and use_model:
        return {"intent": "other", "converse": True, "text": ""}
    spoken = converse(text, run, history, use_model)
    if spoken:
        return {"intent": "other", "text": spoken, "spoken": spoken}
    msg = offline_answer(text, run)
    return {"intent": "other", "text": msg, "spoken": msg}
