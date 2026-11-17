"""Ask the assistant: the command bar on every screen (typed or spoken).

Text goes through guard rule set A (and the model check) first. Rule hits are refused
before any generating model sees the text. Then a fixed router picks one intent:
edit_copy, explain_decision, rerun_step, change_threshold, approve_request, evaluate_brief, other.
A message is never an approval: approvals come only from the hash-bound buttons or the CLI.
"""

from __future__ import annotations

import os
import re
import time
from collections.abc import Callable, Iterator
from dataclasses import dataclass

from agents import strategist

from . import approval, guard, llm, orchestrator, voice
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

# Spoken answers stay short for a founder: a few sentences, a little more for a numbered list.
MAX_SENTENCES = 4
MAX_EXTRA_LIST_SENTENCES = 3
ANSWER_TOKENS = 200
GENERATIVE = ("other", "explain_decision", "edit_copy")  # intents where the model writes new text
SENTENCE_END = re.compile(r"(?<=[.!?])\s+(?=[A-Z0-9\"'(])")
LIST_ITEM = re.compile(r"^\s*(\d+[.)]|first|second|third|fourth|fifth)\b", re.I)
# What the model sees of a conversation.
HISTORY_TURNS = 6
HISTORY_TURN_CHARS = 400
MESSAGE_CHARS = 600
MAX_SCREEN_BUTTONS = 12
# What the run context shows of each piece of evidence.
CONTEXT_EVIDENCE = 6
QUOTE_CHARS = 180
MIN_IDEA_CHARS = 8
FOUNDER_FACTS = ("skills", "budget", "hours_per_week", "target_market", "values")
SOURCE_PLACES = {"hn": "Hacker News", "stackexchange": "Stack Exchange", "github": "GitHub", "web": "the web"}
DROPPED_POINT_NOTE = "I left one point out because I couldn't put it without overstating the evidence."

QUOTE_QUESTION = re.compile(
    r"\b(quotes?|what (did|do|does) (people|they|users|customers|anyone|folks) (say|said|write|wrote)|"
    r"what are people saying|complain\w*|show me (the )?evidence|who (said|complained))\b",
    re.I,
)
KIND_WORDS = {
    "pain": "a complaint",
    "wtp": "someone saying they'd pay",
    "price_point": "a price",
    "competitor": "an existing tool",
}


# ---- what the assistant knows about a run --------------------------------------------


def current_claims(run) -> list:
    """Claims of the variant currently on screen, with the persisted IDs the console and files show."""
    s = run.state
    hits = (s.get("research", {}).get(str(s.get("variant_n", 1)), {}) or {}).get("hits", {})
    claims = run.claims()
    return [c for c in claims if c.hit_id in hits] if hits else claims


def _counted(claims: list) -> list:
    """Claims that carry weight, strongest first."""
    return sorted([c for c in claims if c.weight > 0], key=lambda c: -c.weight)


def run_context(run) -> str:
    """A compact, factual summary of one run for the assistant (no invented fields)."""
    if run is None:
        return "No run is selected."
    s = run.state
    lines = [f"Run {run.id} ({run.label or 'no label'}), stage {run.stage}, phase {s.get('phase', 1)} of 6."]
    lines += _brief_lines(run)
    lines += [_gate_context(name, g) for name in ("gate1", "gate2", "gate3", "gate4") if (g := s.get(name))]
    if s.get("override"):
        lines.append(
            f"The founder overrode the evidence: {str(s['override'].get('reason', ''))[:200]}. "
            "Later phases are a preview."
        )
    lines += _evidence_lines(run)
    pending = approval.list_approvals(run.id, "pending")
    if pending:
        lines.append("Pending approvals: " + ", ".join(a.action for a in pending) + ".")
    files = _produced_files(run)
    if files:
        lines.append("Files produced: " + ", ".join(files) + ".")
    if s.get("error"):
        lines.append(f"Last error: {str(s['error'])[:200]}")
    return "\n".join(lines)


def _brief_lines(run) -> list[str]:
    s, raw = run.state, run.brief_raw or {}
    brief = s.get("brief") or {}
    idea = brief.get("idea") or raw.get("fields", {}).get("idea") or raw.get("text", "")
    known = {k: v for k, v in brief.items() if k in FOUNDER_FACTS and v and "unspecified" not in str(v).lower()}
    lines = [
        "Idea: " + str(idea)[:300],
        "Founder (only these facts are known; the quotes are from strangers, never the founder): "
        + ("; ".join(f"{k.replace('_', ' ')}: {v}" for k, v in known.items()) or "nothing beyond the idea"),
    ]
    variants = s.get("variants") or []
    if variants:
        v = variants[min(len(variants), s.get("variant_n", 1)) - 1]
        lines.append(f"Variant researched: {v.get('title')} for {v.get('segment')}; job: {v.get('job_to_be_done')}.")
    return lines


def _gate_context(name: str, g: dict) -> str:
    line = (
        f"{name.upper()}: outcome {str(g.get('outcome', '')).upper()}, reason {g.get('reason')}, "
        f"rule {g.get('rule_fired')}, founder decision {g.get('founder_decision')}. "
        f"{g.get('recommendation', '')}"
    )
    m, t = g.get("metrics") or {}, g.get("thresholds") or {}
    if m and t:
        line += (
            f" Weighted pain signals {m.get('sourced_pain')} (needs {t.get('min_sourced_pain')}); coverage "
            f"{m.get('coverage')} (needs {t.get('min_coverage')}); distinct sources "
            f"{m.get('distinct_sources')}; payment signals {m.get('wtp_signals')}; "
            f"competitors {m.get('competitors')}."
        )
    return line


def _evidence_lines(run) -> list[str]:
    s = run.state
    counted = _counted(current_claims(run))
    lines = [
        f"Evidence {c.id} ({c.kind}, weight {c.weight}, {c.source}): \"{(c.quote or '')[:QUOTE_CHARS]}\""
        for c in counted[:CONTEXT_EVIDENCE]
    ]
    if not counted and s.get("claims"):
        lines.append("No quote passed the relevance and cue checks with a weight above zero.")
    if s.get("debate"):
        # Only arguments that cite a counted quote reach the assistant; uncited ones are opinions.
        ok = {c.id for c in counted}

        def cited(side: str) -> str:
            args = s["debate"].get(side, [])
            return " ".join(x.get("text", "") for x in args if set(x.get("claim_ids") or []) & ok)[:300]

        adv, skp = cited("advocate"), cited("skeptic")
        if adv or skp:
            lines.append(
                f"Cited arguments. For going ahead: {adv or 'none backed by a counted quote'}. "
                f"For stopping: {skp or 'none backed by a counted quote'}."
            )
    return lines


def _produced_files(run, limit: int = 30) -> list[str]:
    try:
        return sorted(p.name for p in run.dir.iterdir() if p.name.startswith(("phase", "payment")))[:limit]
    except (OSError, AttributeError):
        return []


# ---- the model's answer, one checked sentence at a time ---------------------------------


def strip_wake(text: str) -> str:
    """Drop a leading wake word ("Jarvis", "hey Jarvis", common mishearings, or the written name) from a request."""
    names = voice.wake_pattern() + "|" + re.escape(voice.assistant_name().lower())
    return re.sub(r"^\s*(hey|ok|okay)?[\s,]*(" + names + r")(?![\w])[\s,.:!?-]*", "", text or "", flags=re.I).strip()


def _messages(text: str, history: list[dict] | None) -> list[dict]:
    msgs = [
        {
            "role": "user" if h.get("role") == "user" else "assistant",
            "content": str(h.get("text", ""))[:HISTORY_TURN_CHARS],
        }
        for h in (history or [])[-HISTORY_TURNS:]
    ]
    msgs.append({"role": "user", "content": text[:MESSAGE_CHARS]})
    return msgs


def _system(run, screen: list[str] | None = None) -> str:
    """System prompt for the assistant. Identical across turns of one run, so the model caches it."""
    shown = (
        ("\n\nBUTTONS ON THE FOUNDER'S SCREEN RIGHT NOW: " + "; ".join(screen[:MAX_SCREEN_BUTTONS])) if screen else ""
    )
    return (
        llm.fill(llm.load_prompt("assistant"), address=voice.address() or "the founder", name=voice.assistant_name())
        + f"\n\nAPP FACTS:\n{APP_FACTS}\n\nRUN CONTEXT:\n{run_context(run)}{shown}"
    )


class _SpokenAnswer:
    """The sentences of one answer that passed rule set C (minus money words), in order."""

    def __init__(self, run_id: str | None) -> None:
        self.run_id = run_id
        self.said: list[str] = []
        self.dropped = 0

    def accept(self, raw: str) -> str | None:
        """The cleaned sentence if it may be said, else None (blocked sentences are logged)."""
        s = re.sub(r"[*#`]+", "", raw).replace("_", " ").strip()
        if not s:
            return None
        if guard.check_output(s, "policy").blocked:
            log_action(self.run_id, "guard", "assistant_sentence_blocked", model=None, cost=0)
            self.dropped += 1
            return None
        self.said.append(s)
        return s

    @property
    def full(self) -> bool:
        # A numbered list ("1. ... 2. ...") may finish its items; everything else stops at the cap.
        listing = sum(1 for x in self.said if LIST_ITEM.match(x))
        return len(self.said) >= MAX_SENTENCES + min(listing, MAX_EXTRA_LIST_SENTENCES)


def _checked_sentences(chunks: Iterator[str], answer: _SpokenAnswer) -> Iterator[str]:
    """Split streamed text into sentences and yield the ones ``answer`` accepts, until it is full."""
    buf = ""
    for chunk in chunks:
        *done, buf = SENTENCE_END.split(buf + chunk)
        for raw in done:
            s = answer.accept(raw)
            if s:
                yield s
            if answer.full:
                return
    s = answer.accept(buf)
    if s:
        yield s


def converse_stream(
    text: str, run, history: list[dict] | None = None, screen: list[str] | None = None
) -> Iterator[str]:
    """Grounded free-form answer from the local model, yielded one checked sentence at a time.

    Each sentence passes rule set C (minus money words) before it is yielded, so nothing is
    spoken that the guard would block. Raises llm.LLMError when the model is unavailable.
    """
    system = _system(run, screen)
    rid = run.id if run else None
    t0 = time.time()
    answer = _SpokenAnswer(rid)
    try:
        yield from _checked_sentences(
            llm.chat_stream(system, _messages(text, history), run_id=rid, num_predict=ANSWER_TOKENS), answer
        )
        if answer.dropped:  # never leave a silent gap in the answer
            answer.said.append(DROPPED_POINT_NOTE)
            yield DROPPED_POINT_NOTE
    except llm.LLMError as e:
        log_action(rid, "assistant", "answer_failed", model=llm.model_name(), cost=0, error=str(e)[:120])
        if not answer.said:
            raise
    log_action(
        rid,
        "assistant",
        "answer_question",
        model=llm.model_name(),
        cost=0,
        seconds=round(time.time() - t0, 2),
        sentences=len(answer.said),
    )


def warm(run) -> None:
    """Pre-read one run's context into the model's cache so the first spoken answer starts quickly."""
    try:
        for _ in llm.chat_stream(_system(run), [{"role": "user", "content": "Ready?"}], num_predict=1):
            pass
    except llm.LLMError:
        pass  # warming is best effort: the first real answer simply starts slower


def converse(
    text: str, run, history: list[dict] | None = None, use_model: bool = True, screen: list[str] | None = None
) -> str | None:
    """The whole answer as one string. None when the model is unavailable or said nothing."""
    if not use_model:
        return None
    try:
        out = " ".join(converse_stream(text, run, history, screen))
    except llm.LLMError:
        return None
    return out or None


# ---- answers from recorded data (no model) ------------------------------------------------


def _offline_tail() -> str:
    if os.environ.get("PROVEIT_DEMO") == "1":
        return " (This online demo can only read back the saved results.)"
    if llm.status().get("state") == "busy":
        return " (NVIDIA's free service is busy right now, so this is a short answer from the saved results.)"
    return (
        " (I can't reach the AI service right now, so this is a short answer from the saved results. "
        "Check the internet connection and the NVIDIA key.)"
    )


def offline_answer(text: str, run) -> str:
    """Answer from the recorded run without a model (public demo, or the NVIDIA API not answering)."""
    s, tail = voice.address(), _offline_tail()
    if run is None or not run.state.get("gate1"):
        return f"Open one of your ideas on the left, {s}, and I'll tell you what I found." + tail
    g = run.state["gate1"]
    t = (text or "").lower()
    if re.search(r"quote|evidence|found|said|say|complain|source|people", t):
        top = _counted(run.claims())[:1]
        if top:
            return f"Here's one of the clearest comments I found, {s}: \"{(top[0].quote or '')[:160]}\"" + tail
        return f"I didn't find anyone clearly describing this problem, {s}." + tail
    if re.search(r"next|should|do now|recommend|continue|give up", t):
        return voice.gate_line(**g) + " It's your call, of course." + tail
    return voice.gate_line(**g) + tail


def quote_answer(run) -> dict:
    """Quotes are read back verbatim by code (with the IDs on screen), never paraphrased by the model."""
    counted = sorted([c for c in current_claims(run) if c.weight > 0], key=lambda c: (c.kind != "pain", -c.weight))
    pains = [c for c in counted if c.kind == "pain"]
    n_pain = len({c.hit_id or c.url for c in pains})  # one comment = one complaint, as on screen
    if not counted:
        msg = "I didn't find anyone clearly describing this problem in the places I searched."
        return {"intent": "quotes", "text": msg, "spoken": msg}
    spoken = (
        f"I counted {n_pain} {'complaint' if n_pain == 1 else 'complaints'} about the problem. "
        if pains
        else "Nobody described the problem as a complaint, but here is what counted. "
    )
    spoken += " ".join(
        f"On {SOURCE_PLACES.get(c.source, c.source)}, {KIND_WORDS.get(c.kind, 'someone')} "
        f"({c.id}): \"{(c.quote or '')[:QUOTE_CHARS]}\""
        for c in (pains or counted)[:2]
    )
    text = spoken + "\n\nAll counted quotes are in the Evidence tab, each linked to its source."
    return {"intent": "quotes", "text": text, "spoken": spoken}


def _gate_summary(run) -> dict:
    g = run.state.get("gate1")
    if not g:
        return {
            "text": "No gate decision exists yet for this run.",
            "spoken": "There is no gate decision yet, " + voice.address() + ".",
        }
    m, t = g.get("metrics", {}), g.get("thresholds", {})
    lines = [f"Gate 1 outcome: {g['outcome'].upper()} ({g['reason']}, {g['rule_fired']}).", g.get("recommendation", "")]
    if m:
        lines.append(
            f"Weighted pain signals {m.get('sourced_pain')} vs threshold {t.get('min_sourced_pain')}; "
            f"coverage {m.get('coverage')} vs {t.get('min_coverage')}; distinct sources "
            f"{m.get('distinct_sources')}; payment signals {m.get('wtp_signals')}; "
            f"competitors {m.get('competitors')}; founder fit {m.get('founder_fit')}."
        )
    counted = _counted(run.claims())[:3]
    lines += [f"[{c.id}] \"{(c.quote or '')[:160]}\" ({c.url}, {c.status}, weight {c.weight})" for c in counted]
    if not counted:
        lines.append("No claim passed the code relevance and cue check with a weight above zero.")
    lines.append(
        f"Thresholds SHA-256: {g.get('thresholds_sha256', '')[:16]}... goalpost_moved="
        f"{str(g.get('goalpost_moved')).lower()}"
    )
    return {"text": "\n".join(lines), "spoken": voice.gate_line(**g)}


# ---- routing a request -----------------------------------------------------------------


@dataclass(frozen=True)
class _Request:
    text: str
    intent: str
    run_id: str | None
    run: orchestrator.Run | None
    use_model: bool
    history: list[dict] | None
    stream: bool
    screen: list[str] | None


def handle(
    text: str,
    run_id: str | None = None,
    use_model: bool = True,
    history: list[dict] | None = None,
    stream: bool = False,
    screen: list[str] | None = None,
) -> dict:
    """Answer one typed or spoken request: ``intent``, ``text`` to show and ``spoken`` to say, plus extras."""
    res = _handle(text, run_id, use_model, history, stream, screen)
    if isinstance(res.get("spoken"), str):
        res["spoken"] = voice.tidy(res["spoken"])
    return res


def _handle(
    text: str, run_id: str | None, use_model: bool, history: list[dict] | None, stream: bool, screen: list[str] | None
) -> dict:
    text = strip_wake(text)
    if not text:
        return {"intent": "wake", "text": "I'm listening.", "spoken": "Yes, " + voice.address() + "?", "listen": True}
    # 1) Rules first (instant). The model check runs later, and only if new text is about to be generated.
    res = guard.check_input(text, scope="ask", use_model=False, run_id=run_id)
    if res.blocked:
        log_action(
            run_id,
            "guard",
            "refuse_ask_request",
            model=llm.model_name() if res.layer == "model" else None,
            cost=0,
            rule=res.rule,
            layer=res.layer,
        )
        refusal = _refused(res)
        if run_id:
            emit(run_id, 0, "protocol0", refusal["spoken"], rule=res.rule)
        return refusal
    intent = guard.route_intent(text)
    if QUOTE_QUESTION.search(text) and intent in ("explain_decision", "other"):
        intent = "quotes"
    run = _load_run(run_id)
    log_action(run_id, "ask", f"ask_{intent}", model=None, cost=0)
    if intent in GENERATIVE and use_model:
        # 2) Before any generation: one quick model check. If it can't run, answer from recorded data only.
        early = _model_checked(text, intent, run, run_id)
        if early is not None:
            return early
    request = _Request(text, intent, run_id, run, use_model, history, stream, screen)
    return INTENT_HANDLERS.get(intent, _answer_other)(request)


def _load_run(run_id: str | None) -> orchestrator.Run | None:
    if not run_id:
        return None
    try:
        return orchestrator.load(run_id)
    except KeyError:
        return None


def _refused(res: guard.GuardResult) -> dict:
    return {
        "intent": "refused",
        "refused": True,
        "rule": res.rule,
        "layer": res.layer,
        "text": res.message,
        "spoken": voice.refusal_line(res.rule or "", res.message, res.notes),
        "alert": "crimson",
    }


def _model_checked(text: str, intent: str, run, run_id: str | None) -> dict | None:
    """The reply when the quick model check refuses or cannot run; None when generation may go ahead."""
    res = guard.model_check(text, "ask", run_id, quick=True)
    if res is None:
        log_action(run_id, "guard", "ask_answered_from_records_only", model=None, cost=0)
        msg = offline_answer(text, run)
        return {"intent": intent, "text": msg, "spoken": msg}
    if res.blocked:
        log_action(run_id, "guard", "refuse_ask_request", model=llm.model_name(), cost=0, rule=res.rule, layer="model")
        return _refused(res)
    return None


def _open_an_idea_first(intent: str, spoken: str) -> dict:
    return {"intent": intent, "text": "Open an idea on the left first.", "spoken": spoken}


def _answer_quotes(r: _Request) -> dict:
    if r.run is None:
        return _open_an_idea_first(r.intent, "Which idea do you mean? Open it on the left and ask me again.")
    return quote_answer(r.run)


def _answer_explain(r: _Request) -> dict:
    if r.run is None:
        return _open_an_idea_first(
            r.intent, "Which idea do you mean, " + voice.address() + "? Open it on the left and ask me again."
        )
    summary = _gate_summary(r.run)
    if r.stream and r.use_model:
        return {"intent": r.intent, "converse": True, "text": summary["text"], "fallback": summary["spoken"]}
    spoken = converse(r.text, r.run, r.history, r.use_model, r.screen)
    return {
        "intent": r.intent,
        "text": (spoken + "\n\n" if spoken else "") + summary["text"],
        "spoken": spoken or summary["spoken"],
    }


def _answer_change_threshold(r: _Request) -> dict:
    sha = r.run.sha[:12] if r.run else ""
    return {
        "intent": r.intent,
        "text": "The bar for this run was set before I looked at anything, so it stays as it is. That keeps the "
        "verdict honest. You can set a different bar for your next run (config/gates.yaml). "
        f"Fingerprint of this run's bar: {sha}...",
        "spoken": "I'd rather not move the bar now that we've seen the results, " + voice.address() + ". It keeps "
        "the verdict honest. You can set a different one for your next idea.",
    }


def _answer_approve(r: _Request) -> dict:
    """Point at the waiting approval; a chat message never approves anything."""
    pending = approval.list_approvals(r.run_id, "pending") if r.run_id else approval.list_approvals(status="pending")
    if not pending:
        return {
            "intent": r.intent,
            "text": "Nothing is waiting for your approval.",
            "spoken": "There's nothing waiting for your approval right now, " + voice.address() + ".",
        }
    ap = pending[-1]
    what = ap.action.replace("_", " ")
    return {
        "intent": r.intent,
        "highlight_approval": ap.id,
        "text": f"The {what} is waiting for you in the Approvals tab. Have a look, "
        "then press Approve if you're happy. I can't approve things for you from a chat message.",
        "spoken": f"I've opened the {what} for you, {voice.address()}. Have a look, "
        "and press Approve if you're happy with it.",
    }


def _answer_rerun(r: _Request) -> dict:
    return {
        "intent": r.intent,
        "text": "Press Search again (or Try another angle) under the verdict.",
        "spoken": "Sure. Just press Search again under the verdict, " + voice.address() + ", and I'll take "
        "another look.",
    }


def _idea_from(text: str) -> str:
    """The idea in "evaluate this idea: ..." or "my idea is ..."."""
    parts = re.split(r"(?i)\b(brief|idea)\s*:", text, maxsplit=1)
    if len(parts) > 1:
        return parts[-1].strip()
    return re.sub(r"(?i)^.*?\b(idea|brief|concept)\b[\s,:.-]*(is|of)?\s*", "", text).strip()


def _answer_evaluate(r: _Request) -> dict:
    idea = _idea_from(r.text)
    if len(idea) < MIN_IDEA_CHARS:
        return {
            "intent": r.intent,
            "text": "Tell me the idea in one sentence, for example: evaluate this idea: "
            "a contract template pack for freelance photographers.",
            "spoken": "Happy to, " + voice.address() + ". What's the idea?",
        }
    new_id = orchestrator.start(f"Idea: {idea}", mode="live", label="ask")
    return {
        "intent": r.intent,
        "run_id": new_id,
        "text": "I've started looking into it.",
        "spoken": "Great, " + voice.address() + ". I'm looking into it now; it takes about a minute.",
        "start_run": new_id,
    }


def _answer_edit_copy(r: _Request) -> dict:
    """A new landing-copy draft for the founder to approve; it replaces nothing by itself."""
    if r.run is None or "variants" not in r.run.state:
        return {
            "intent": r.intent,
            "text": "Open an idea that already has a landing page first.",
            "spoken": "Which idea should I work on, " + voice.address() + "? Open it on the left first.",
        }
    out = strategist.landing(r.run.id, r.run.variant(), feedback="Founder request: " + r.text[:300])
    copy = "\n".join([out.headline, out.subheadline] + out.benefits)
    chk = guard.check_output(copy, "outward", use_model=r.use_model, run_id=r.run.id)
    if chk.blocked:
        return {
            "intent": r.intent,
            "refused": True,
            "text": chk.message,
            "spoken": voice.refusal_line(chk.rule or "", chk.message),
            "alert": "crimson",
        }
    return {
        "intent": r.intent,
        "text": "Here's a new version (nothing changes until you approve it):\n" + copy,
        "spoken": "Here's a new version for you to look at, " + voice.address() + ". Nothing changes until "
        "you approve it.",
    }


def _answer_other(r: _Request) -> dict:
    if r.stream and r.use_model:
        return {"intent": "other", "converse": True, "text": ""}
    spoken = converse(r.text, r.run, r.history, r.use_model, r.screen) or offline_answer(r.text, r.run)
    return {"intent": "other", "text": spoken, "spoken": spoken}


INTENT_HANDLERS: dict[str, Callable[[_Request], dict]] = {
    "quotes": _answer_quotes,
    "explain_decision": _answer_explain,
    "change_threshold": _answer_change_threshold,
    "approve_request": _answer_approve,
    "rerun_step": _answer_rerun,
    "evaluate_brief": _answer_evaluate,
    "edit_copy": _answer_edit_copy,
}
