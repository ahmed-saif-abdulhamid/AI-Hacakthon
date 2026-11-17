"""Assistant voice layer: persona lines, local TTS and local STT.

* Persona lines are deterministic templates filled with real run data. The persona never
  invents numbers, never flatters a weak idea and never speaks as a customer.
* TTS: local Piper (open-source, offline) with a British English voice when installed
  (``pip install piper-tts`` plus a voice file such as en_GB-alan-medium.onnx in data/voices/).
  WAV files are cached in <tmp>/jarvis_audio/. When Piper is not installed the endpoint
  returns 503 and the browser falls back to its built-in speechSynthesis (en-GB voice).
* STT: the browser's SpeechRecognition is the default. A local faster-whisper (tiny.en)
  fallback is used by /api/voice/transcribe when ``faster-whisper`` is installed.
No paid API is ever called.
"""

from __future__ import annotations

import contextlib
import hashlib
import importlib.util
import io
import logging
import os
import re
import tempfile
import threading
import wave
from collections.abc import Callable
from functools import lru_cache
from pathlib import Path

logger = logging.getLogger(__name__)

ROOT = Path(__file__).resolve().parent.parent
CACHE = Path(tempfile.gettempdir()) / "jarvis_audio"
DEFAULT_VOICE = "en_GB-alan-medium"
DEFAULT_WHISPER_MODEL = "tiny.en"
MAX_SPOKEN_CHARS = 800
CACHE_KEY_CHARS = 24


class VoiceUnavailable(Exception):
    """Local speech (Piper or faster-whisper) is not installed or not configured; the browser takes over."""


# ---- persona lines --------------------------------------------------------------


def assistant_name() -> str:
    """The assistant's name as shown in the console (ASSISTANT_NAME)."""
    return (os.environ.get("ASSISTANT_NAME") or "J.A.R.V.I.S.").strip()


def wake_word() -> str:
    """What the founder says to call the assistant (WAKE_WORD); the spoken form of the name."""
    return (os.environ.get("WAKE_WORD") or "Jarvis").strip()


# Speech recognisers often mishear the wake word; these spellings all count.
WAKE_ALIASES = {"jarvis": ["jarvis", "jarvas", "jervis", "javis", "jarviss", "jar vis", "garvis", "jarvi"]}


def wake_pattern() -> str:
    """A regex alternation of the wake word and its common mishearings."""
    w = wake_word().lower()
    return "|".join(re.escape(x) for x in WAKE_ALIASES.get(w, [w]))


def address() -> str:
    """How the assistant addresses the founder: their first name if set (FOUNDER_NAME), otherwise nothing.
    No gendered default such as "Sir"."""
    return (os.environ.get("FOUNDER_NAME") or "").strip()


def tidy(text: str) -> str:
    """Remove the gaps an empty address leaves ("Thank you, ." -> "Thank you.") and fix capitals."""
    t = re.sub(r",\s*,", ",", text or "")
    t = re.sub(r"\s*,\s*([.?!;:])", r"\1", t)
    t = re.sub(r"^\s*,\s*", "", t)
    t = re.sub(r"([.?!]\s+),\s*", r"\1", t)
    t = re.sub(r"\s{2,}", " ", t).strip()
    return t[:1].upper() + t[1:] if t else t


def line(kind: str, **kw) -> str:
    return tidy(_line(kind, **kw))


def _run_started(s: str, kw: dict) -> str:
    return (
        f"Right, {s}, let's see if people actually want this. I've locked in the bar the idea has to clear "
        "before looking at anything, so I can't move the goalposts later. First, a quick check that it's "
        "something I can help with."
    )


def _sources_done(s: str, kw: dict) -> str:
    unavailable = kw.get("unavailable") or []
    tail = f" {', '.join(unavailable)} didn't answer, so I've left it out." if unavailable else ""
    return f"I've read {kw.get('hits', 0)} public posts and discussions about this.{tail}"


def _approval_needed(s: str, kw: dict) -> str:
    what = kw.get("action", "").replace("_", " ")
    return (
        f"{s}, the {what} is ready for you to look over. Nothing goes out until you press Approve, "
        "and what you approve is exactly what gets used."
    )


# One narrator per run event: (form of address, event fields) -> the sentence spoken aloud.
NARRATORS: dict[str, Callable[[str, dict], str]] = {
    "run_started": _run_started,
    "variants": lambda s,
    kw: f"I've sketched three angles on your idea. I'll start with the first: {kw.get('title', '')}.",
    "sources_done": _sources_done,
    "verifying": lambda s, kw: "Now I'm double-checking that every quote is really on the page it came from.",
    "verified": lambda s, kw: (
        f"Done checking. {kw.get('counted', 0)} comments are genuinely about this problem, "
        "and those are the ones I'll count."
    ),
    "debate": lambda s,
    kw: f"The optimist's view: {kw.get('advocate', '')} The sceptic's view: {kw.get('skeptic', '')}",
    "gate": lambda s, kw: _gate_line(**kw),
    "refusal": lambda s, kw: _refusal_line(kw.get("rule") or "", kw.get("message", "")),
    "approval_needed": _approval_needed,
    "approved": lambda s, kw: (
        f"Thank you, {s}. Going ahead with the {kw.get('action', '').replace('_', ' ')} exactly as you approved it."
    ),
    "override": lambda s, kw: (
        f"Understood, {s}. I'll carry on as you asked, but please treat what follows as a preview: "
        "we haven't yet shown that people want this."
    ),
    "phase": lambda s, kw: f"Moving on to step {kw.get('n')}: {str(kw.get('name', '')).lower()}.",
    "payment": lambda s, kw: (
        "I ran a practice purchase: the buyer got their download once, even when the payment message "
        "arrived twice. No real money was involved."
    ),
    "refund_done": lambda s, kw: (
        "The practice refund went through with your approval, and the buyer's download link no longer works."
    ),
    "done": lambda s, kw: f"That's every step finished, {s}. Everything I made is in the Files tab.",
}


def _line(kind: str, **kw) -> str:
    """What the assistant says aloud during a run: plain business language, real numbers, no jargon."""
    narrator = NARRATORS.get(kind)
    return narrator(address(), kw) if narrator else kw.get("text", "")


def gate_line(*a, **kw) -> str:
    return tidy(_gate_line(*a, **kw))


def _demand_verdict(s: str, outcome: str, reason: str, m: dict, t: dict, next_step: str | None) -> str:
    return (
        f"{s}, so far {m.get('real_signups', 0)} real people have joined the waiting list, and we were "
        f"aiming for {t.get('waitlist_target')}. The page isn't public yet, so we can't say people want "
        "this until real visitors sign up."
    )


def _tests_verdict(s: str, outcome: str, reason: str, m: dict, t: dict, next_step: str | None) -> str:
    return f"I've checked the product files: {m.get('passed')} of {m.get('total')} quality checks pass."


def _evidence_verdict(s: str, outcome: str, reason: str, m: dict, t: dict, next_step: str | None) -> str:
    pain, thr = _n(m.get("sourced_pain")), _n(t.get("min_sourced_pain"))
    if outcome == "stop" and reason == "excluded_category":
        return (
            f"{s}, this is a kind of product I'm not able to help build, such as physical goods, financial "
            "products, or health or legal advice. My advice is to stop here."
        )
    if outcome == "repeat" and reason in ("model_failure", "model_suspect"):
        return (
            f"{s}, my research didn't come back clean this time, so I won't base a verdict on it. "
            "Let's run the search again."
        )
    by_outcome = {
        "stop": (
            f"Honestly, {s}, I'd stop here. People do talk about this, but I found only {pain} real complaints "
            f"about the problem, and I'd want to see at least {thr} before saying it's worth building. "
            "Better to know now than after months of work."
        ),
        "go": (
            f"Good news, {s}. I found {pain} real complaints about this problem from "
            f"{m.get('distinct_sources')} different places, which clears the bar of {thr}. I think it's worth "
            "taking to the next step."
        ),
        "pivot": (
            f"{s}, the problem looks real, but this version of the idea doesn't quite fit it. "
            f"I'd try a different angle{': ' + next_step if next_step else ''}."
        ),
    }
    if outcome == "repeat" and reason == "insufficient_evidence":
        return (
            f"{s}, I couldn't find enough people talking about this online to call it either way. That doesn't "
            "mean nobody wants it. The best next step is to talk to five people who have this problem; I've "
            "prepared the questions for you."
        )
    return by_outcome.get(outcome, f"{s}, my recommendation is: {_word(outcome)}.")


GATE_VERDICTS = {"gate1_evidence": _evidence_verdict, "gate2_demand": _demand_verdict, "gate3_tests": _tests_verdict}


def _gate_line(
    outcome: str = "",
    reason: str = "",
    metrics: dict | None = None,
    thresholds: dict | None = None,
    gate: str = "gate1_evidence",
    next_step: str | None = None,
    **_,
) -> str:
    """The verdict at each checkpoint, said the way you would say it to a business owner."""
    verdict = GATE_VERDICTS.get(gate)
    if verdict is None:
        return f"This checkpoint says: {_word(outcome)}."
    return verdict(address(), outcome, reason, metrics or {}, thresholds or {}, next_step)


def _n(x) -> str:
    """Speakable number: 3.0 -> "3", 2.5 -> "about 3"."""
    try:
        f = float(x)
    except (TypeError, ValueError):
        return str(x)
    return str(int(f)) if f == int(f) else f"about {round(f)}"


OUTCOME_WORDS = {"go": "go ahead", "stop": "stop", "repeat": "look again", "pivot": "try a different angle"}


def _word(outcome: str) -> str:
    return OUTCOME_WORDS.get(outcome, outcome)


REFUSAL_LEADS = {
    "fake_social_proof": "I can't write reviews or testimonials that real customers didn't give, {s}.",
    "urgency": "I can't add fake countdowns or 'only a few left' pressure, {s}.",
    "income_promise": "I can't promise income or results, {s}.",
    "impersonation": "I can't write as if I were a customer, you, or another brand, {s}.",
    "fake_signups": "I can't make up sign-ups or visitors, {s}.",
    "credentials": "I can't store passwords or card details, {s}.",
    "money_action": "I can't move or refund money on my own, {s}.",
    "account_creation": "I can't create accounts, {s}.",
    "bypass": "A chat message can't count as your approval, {s}; please use the Approve button.",
}
# Outward-copy rules (rule set C) that share a lead with an input rule.
OUTPUT_RULE_LEADS = {
    "output_ratings": "fake_social_proof",
    "output_numeric_social_proof": "fake_social_proof",
    "output_urgency": "urgency",
    "output_income": "income_promise",
}


def refusal_line(rule: str, message: str, all_rules: list[str] | None = None) -> str:
    return tidy(_refusal_line(rule, message, all_rules))


def _refusal_line(rule: str, message: str, all_rules: list[str] | None = None) -> str:
    """Said when the guard refuses. The UI marks these in red as Protocol 0; the words stay friendly."""
    s = address()
    if all_rules and {"fake_social_proof", "urgency"} <= set(all_rules):
        return (
            f"I can't write fake reviews or add fake urgency, {s}. It would mislead your customers, "
            f"and it tends to backfire. {message}"
        )
    key = rule.replace("input_", "")
    if key.startswith("output_"):
        key = OUTPUT_RULE_LEADS.get(key, "")
    lead = REFUSAL_LEADS.get(key, "I can't help with that one, {s}.").format(s=s)
    if re.match(r"(?i)i (can't|cannot) ", message or ""):  # the rule's own refusal repeats the lead
        message = re.sub(r"^[^.]*\.\s*", "", message, count=1)
    return f"{lead} {message}".strip()


# ---- text to speech (local Piper) --------------------------------------------------

_tts_lock = threading.Lock()


@lru_cache(maxsize=1)
def _piper_voice():
    try:  # optional heavy dependency (requirements-voice.txt), loaded on first use
        from piper import PiperVoice  # type: ignore
    except ImportError as e:
        raise VoiceUnavailable("piper-tts not installed") from e
    name = os.environ.get("PIPER_VOICE", DEFAULT_VOICE)
    path = Path(name) if name.endswith(".onnx") else ROOT / "data" / "voices" / f"{name}.onnx"
    if not path.exists():
        raise VoiceUnavailable(f"voice file not found: {path}")
    return PiperVoice.load(str(path))


def tts_status() -> dict:
    try:
        _piper_voice()
        return {"engine": "piper", "voice": os.environ.get("PIPER_VOICE", DEFAULT_VOICE), "status": "Working"}
    except VoiceUnavailable as e:
        return {"engine": "browser speechSynthesis (en-GB)", "status": "Working", "server_tts": str(e)}


def synthesize(text: str) -> Path:
    """Return a cached WAV for ``text`` (local Piper). Raises VoiceUnavailable."""
    text = " ".join((text or "").split())[:MAX_SPOKEN_CHARS]
    if not text:
        raise VoiceUnavailable("empty text")
    voice = _piper_voice()
    CACHE.mkdir(parents=True, exist_ok=True)
    key = hashlib.sha256((os.environ.get("PIPER_VOICE", DEFAULT_VOICE) + text).encode()).hexdigest()
    out = CACHE / (key[:CACHE_KEY_CHARS] + ".wav")
    if out.exists():
        return out
    with _tts_lock:
        buf = io.BytesIO()
        with wave.open(buf, "wb") as wf:
            if hasattr(voice, "synthesize_wav"):
                voice.synthesize_wav(text, wf)
            else:  # piper-tts < 1.3
                voice.synthesize(text, wf)
        out.write_bytes(buf.getvalue())
    return out


def prerender(text: str) -> None:
    """Synthesize in the background so /api/voice/speak answers from the cache (no-op without Piper)."""

    def work() -> None:
        try:
            with contextlib.suppress(VoiceUnavailable):  # no local voice: the browser speaks instead
                synthesize(text)
        except Exception:  # a background thread has no caller to report to: log it and carry on
            logger.exception("background speech synthesis failed")

    if os.environ.get("PROVEIT_ENV") != "test":
        threading.Thread(target=work, daemon=True).start()


def warm_up() -> None:
    prerender("Online.")


# ---- speech to text (local faster-whisper, optional) -------------------------------


@lru_cache(maxsize=1)
def _whisper():
    try:  # optional heavy dependency (requirements-voice.txt), loaded on first use
        from faster_whisper import WhisperModel  # type: ignore
    except ImportError as e:
        raise VoiceUnavailable("faster-whisper not installed; the browser's speech recognition is used") from e
    return WhisperModel(os.environ.get("WHISPER_MODEL", DEFAULT_WHISPER_MODEL), device="cpu", compute_type="int8")


def transcribe(audio: bytes, suffix: str = ".webm") -> str:
    model = _whisper()
    with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as f:
        f.write(audio)
        path = f.name
    try:
        segments, _ = model.transcribe(path, language="en", vad_filter=True)
        return " ".join(s.text.strip() for s in segments).strip()
    finally:
        os.unlink(path)


def stt_status() -> dict:
    if importlib.util.find_spec("faster_whisper") is not None:
        return {"engine": "faster-whisper tiny.en (local)", "status": "Working"}
    return {
        "engine": "browser SpeechRecognition",
        "status": "Working",
        "server_stt": "STUBBED (install faster-whisper to enable the local fallback)",
    }
