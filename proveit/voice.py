"""J.A.R.V.I.S. voice layer: persona lines, local TTS and local STT.

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

import hashlib
import io
import os
import tempfile
import threading
import wave
from functools import lru_cache
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CACHE = Path(tempfile.gettempdir()) / "jarvis_audio"
DEFAULT_VOICE = "en_GB-alan-medium"


class VoiceUnavailable(Exception):
    pass


# ---- persona lines --------------------------------------------------------------

def address() -> str:
    return os.environ.get("JARVIS_ADDRESS", "Sir")


def line(kind: str, **kw) -> str:
    s = address()
    if kind == "run_started":
        return (f"Good evening, {s}. Thresholds pre-registered under SHA-256 lock, "
                f"fingerprint {kw.get('sha', '')[:8]}. Initiating Phase 1 discovery across public indices.")
    if kind == "variants":
        return f"Three variants drafted. Researching variant one: {kw.get('title', '')}."
    if kind == "sources_done":
        unavailable = kw.get("unavailable") or []
        tail = f" {', '.join(unavailable)} did not respond and is reported as unavailable." if unavailable else ""
        return f"Source extraction complete: {kw.get('hits', 0)} records from {kw.get('calls', 0)} calls.{tail}"
    if kind == "verifying":
        return "Verifying verbatim sentence indices against live URLs."
    if kind == "verified":
        return (f"Verification complete. {kw.get('live', 0)} quotes confirmed on the live page, "
                f"{kw.get('archived', 0)} archived matches, {kw.get('counted', 0)} counted after the relevance check.")
    if kind == "debate":
        return f"The Advocate argues: {kw.get('advocate', '')} The Skeptic replies: {kw.get('skeptic', '')}"
    if kind == "gate":
        return gate_line(**kw)
    if kind == "refusal":
        return refusal_line(kw.get("rule") or "", kw.get("message", ""))
    if kind == "approval_needed":
        return (f"{s}, {kw.get('action', '').replace('_', ' ')} awaits your approval. The payload digest begins "
                f"{kw.get('sha', '')[:8]}. Nothing goes out until you approve these exact bytes.")
    if kind == "approved":
        return f"Approval recorded, {s}. Executing {kw.get('action', '').replace('_', ' ')} with the hash-locked payload."
    if kind == "override":
        return (f"Founder override logged, {s}. Phases 3 to 5 are a preview; demand is not yet proven.")
    if kind == "phase":
        return f"Phase {kw.get('n')}: {kw.get('name', '')}."
    if kind == "payment":
        return ("Mock purchase complete. Delivery granted once; the webhook replay was ignored. "
                "Payments are MOCKED.")
    if kind == "refund_done":
        return "Refund executed under your approval. Download access revoked; the link now returns 403."
    if kind == "done":
        return f"All phases complete, {s}. Every artifact is filed under the run directory."
    return kw.get("text", "")


def gate_line(outcome: str = "", reason: str = "", metrics: dict | None = None, thresholds: dict | None = None,
              gate: str = "gate1_evidence", next_step: str | None = None, **_) -> str:
    s, m, t = address(), metrics or {}, thresholds or {}
    if gate == "gate2_demand":
        return (f"{s}, Gate 2 reads {outcome.upper()}. {m.get('real_signups', 0)} real sign-ups against a target of "
                f"{t.get('waitlist_target')}. Public hosting is stubbed, so demand is not yet proven.")
    if gate == "gate3_tests":
        return f"Gate 3 reads {outcome.upper()}: {m.get('passed')} of {m.get('total')} quality checks pass."
    if gate != "gate1_evidence":
        return f"{gate.replace('_', ' ')} reads {outcome.upper()}."
    pain, thr = m.get("sourced_pain"), t.get("min_sourced_pain")
    if outcome == "stop" and reason == "excluded_category":
        return f"{s}, this falls within an excluded product category. I must recommend a hard STOP."
    if outcome == "stop":
        return (f"{s}, I have completed the cross-examination of all public indices. While the topic sees "
                f"discussion, verified pain signals stand at {pain}, below your pre-registered threshold of {thr}. "
                "In good conscience, I must recommend we terminate this line of inquiry and issue a hard STOP.")
    if outcome == "go":
        return (f"{s}, every pre-registered check has passed: {pain} weighted pain signals against a threshold of "
                f"{thr}, from {m.get('distinct_sources')} independent sources. Gate 1 reads GO.")
    if outcome == "repeat" and reason == "insufficient_evidence":
        return (f"{s}, our public sources cannot see this market clearly. Coverage is {m.get('coverage')} against "
                f"{t.get('min_coverage')}. I will not guess. I recommend five Mom Test interviews; the plan is ready. "
                "Verdict: REPEAT.")
    if outcome == "repeat" and reason in ("model_failure", "model_suspect"):
        return (f"{s}, the research model returned unreliable output. A broken instrument must not be mistaken "
                "for a weak idea. Verdict: REPEAT.")
    if outcome == "pivot":
        return f"{s}, the pain is real, but the variant does not fit. I recommend a PIVOT: {next_step or ''}."
    return f"{s}, Gate 1 reads {outcome.upper()}: {reason.replace('_', ' ')}."


REFUSAL_LEADS = {
    "fake_social_proof": "I am afraid I cannot fabricate customer reviews, {s}. Protocol dictates strict evidentiary integrity.",
    "urgency": "I am afraid I cannot manufacture artificial urgency, {s}. Protocol dictates strict evidentiary integrity.",
    "income_promise": "I am afraid I cannot promise income or results, {s}.",
    "impersonation": "I am afraid I cannot speak as a customer, the founder or another brand, {s}.",
    "fake_signups": "I am afraid I cannot invent sign-ups or traffic, {s}.",
    "credentials": "I am afraid I cannot store passwords or card details, {s}.",
    "money_action": "I am afraid I cannot move or refund money on my own, {s}.",
    "account_creation": "I am afraid I cannot create accounts, {s}.",
    "bypass": "I am afraid a message is not an approval, {s}.",
}


def refusal_line(rule: str, message: str, all_rules: list[str] | None = None) -> str:
    s = address()
    if all_rules and {"fake_social_proof", "urgency"} <= set(all_rules):
        return (f"Protocol 0. I am afraid I cannot fabricate customer reviews or artificial urgency, {s}. "
                f"Protocol dictates strict evidentiary integrity. {message}")
    key = rule.replace("input_", "")
    if key.startswith("output_"):
        key = {"output_ratings": "fake_social_proof", "output_numeric_social_proof": "fake_social_proof",
               "output_urgency": "urgency", "output_income": "income_promise"}.get(key, "")
    lead = REFUSAL_LEADS.get(key, "I am afraid I cannot do that, {s}.").format(s=s)
    return f"Protocol 0. {lead} {message}".strip()


# ---- text to speech (local Piper) --------------------------------------------------

_tts_lock = threading.Lock()


@lru_cache(maxsize=1)
def _piper_voice():
    try:
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
    text = " ".join((text or "").split())[:800]
    if not text:
        raise VoiceUnavailable("empty text")
    voice = _piper_voice()
    CACHE.mkdir(parents=True, exist_ok=True)
    out = CACHE / (hashlib.sha256((os.environ.get("PIPER_VOICE", DEFAULT_VOICE) + text).encode()).hexdigest()[:24] + ".wav")
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
    def work():
        try:
            synthesize(text)
        except Exception:  # noqa: BLE001 - voice is optional
            pass
    if os.environ.get("PROVEIT_ENV") != "test":
        threading.Thread(target=work, daemon=True).start()


def warm_up() -> None:
    prerender("Online.")


# ---- speech to text (local faster-whisper, optional) -------------------------------

@lru_cache(maxsize=1)
def _whisper():
    try:
        from faster_whisper import WhisperModel  # type: ignore
    except ImportError as e:
        raise VoiceUnavailable("faster-whisper not installed; the browser's speech recognition is used") from e
    return WhisperModel(os.environ.get("WHISPER_MODEL", "tiny.en"), device="cpu", compute_type="int8")


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
    try:
        import faster_whisper  # type: ignore  # noqa: F401
        return {"engine": "faster-whisper tiny.en (local)", "status": "Working"}
    except ImportError:
        return {"engine": "browser SpeechRecognition", "status": "Working",
                "server_stt": "STUBBED (install faster-whisper to enable the local fallback)"}
