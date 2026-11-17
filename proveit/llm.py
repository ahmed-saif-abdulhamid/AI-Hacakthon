"""Client for open-weight models through an OpenAI-compatible API. Two providers:

* ``ollama`` (the Docker default): a local model served by Ollama, downloaded on first start by
  ``docker compose up``. No key, no account, nothing leaves the computer. ``OLLAMA_MODEL``
  (default ``qwen3:4b-instruct-2507-q4_K_M``), ``OLLAMA_URL`` (default ``http://localhost:11434``).
* ``nvidia``: open-weight NVIDIA Nemotron on build.nvidia.com's free developer tier
  (``NVIDIA_API_KEY``, roughly 40 requests a minute). Override the model with ``NVIDIA_MODEL``.

``LLM_PROVIDER`` picks one; unset, a configured NVIDIA key selects ``nvidia``, otherwise ``ollama``.
* Structured calls send the Pydantic JSON schema as ``response_format`` (constrained output),
  temperature 0 and a fixed seed; one retry on invalid JSON, then ``LLMError`` (the gate turns
  that into REPEAT/model_failure).
* Every request has a timeout, busy or unreachable servers are retried with bounded back-off, and
  ``LLMError.retryable`` tells callers whether trying again later can help.
* The model has no tools: it only returns data. Only orchestrator code calls functions.
"""

from __future__ import annotations

import contextlib
import json
import os
import re
import threading
import time
from collections.abc import Callable, Iterator
from pathlib import Path
from typing import TypeVar

import httpx
from pydantic import BaseModel, ValidationError

from . import metrics
from .log import log_action

ROOT = Path(__file__).resolve().parent.parent
PROMPTS = ROOT / "prompts"
NVIDIA_URL = "https://integrate.api.nvidia.com/v1"
DEFAULT_MODEL = "nvidia/nemotron-3-ultra-550b-a55b"
OLLAMA_URL = "http://localhost:11434"
OLLAMA_MODEL = "qwen3:4b-instruct-2507-q4_K_M"
FAKE_MODEL_NAME = "fake-llm-tests-only"

# Timeouts (seconds). Guard checks wait briefly for the hosted model; a local model on a CPU needs longer.
DEFAULT_TIMEOUT_SECONDS = 120.0
QUICK_TIMEOUT_SECONDS = {"ollama": 45.0, "nvidia": 10.0}
OLLAMA_STATUS_TIMEOUT_SECONDS = 2.0

# Retries: HTTP statuses worth retrying (rate limit and transient server errors) and their bounds.
RETRY_STATUSES = (429, 500, 502, 503, 504)
TRANSIENT_ERRORS = (httpx.TimeoutException, httpx.NetworkError)
MAX_POST_ATTEMPTS = 10
MAX_STATUS_RETRIES = 5
MAX_TRANSPORT_RETRIES = 2
STREAM_ATTEMPTS = 4
JSON_ATTEMPTS = 2
BACKOFF_BASE_SECONDS = 3.0
BACKOFF_CAP_SECONDS = 20.0
RETRY_AFTER_CAP_SECONDS = 30.0

# Client-side pacing for the shared free tier.
DEFAULT_RPM = 30
DEFAULT_MAX_CONCURRENCY = 2
RATE_WINDOW_SECONDS = 60.0
RATE_POLL_CAP_SECONDS = 5.0
RATE_SLACK_SECONDS = 0.05

# Request shape.
SEED = 7
MIN_JSON_TOKENS = 256
JSON_TOKEN_HEADROOM = 2  # max_tokens = budget x headroom, so a long answer is not cut mid-JSON
STREAM_TEMPERATURE = 0.3
STREAM_TOKEN_HEADROOM = 3
# Request options tried in order: drop the ones a model rejects with HTTP 400.
OPTIONAL_FIELDS = ("chat_template_kwargs", "response_format")

HEALTH_MEMORY_SECONDS = 90.0  # how long a failed call colours the status shown in the console
CHARS_PER_TOKEN = 4

T = TypeVar("T", bound=BaseModel)
Backend = Callable[[str, str, dict, str], str]


class LLMError(Exception):
    """The model could not give a usable answer.

    ``retryable`` is True when the same request may succeed later without any change: the server
    rate-limited us (HTTP 429), was busy or failing transiently (HTTP 5xx in ``RETRY_STATUSES``), or
    could not be reached in time (timeout, connection error). It is False for problems that a retry
    cannot fix: a missing key, no model in the hosted demo, a rejected request, or invalid JSON.
    """

    def __init__(self, message: str, *, retryable: bool = False) -> None:
        super().__init__(message)
        self.retryable = retryable


def _error(message: str, *, retryable: bool) -> LLMError:
    """Build an LLMError and count it for alerting."""
    metrics.increment("llm_call_failed", retryable=retryable)
    return LLMError(message, retryable=retryable)


_backend: Backend | None = None
_usage_lock = threading.Lock()
_usage: dict[str, dict] = {}


def _load_dotenv() -> None:
    """Read KEY=VALUE lines from the untracked .env (no dependency); real env vars win."""
    p = ROOT / ".env"
    if os.environ.get("PROVEIT_ENV") == "test" or not p.exists():
        return
    for line in p.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))


_load_dotenv()


# ---- provider settings -------------------------------------------------------------


def provider() -> str:
    chosen = os.environ.get("LLM_PROVIDER", "").strip().lower()
    if chosen in ("ollama", "nvidia"):
        return chosen
    return "nvidia" if os.environ.get("NVIDIA_API_KEY", "").strip() else "ollama"


def model_name() -> str:
    if _backend is not None:
        return FAKE_MODEL_NAME
    if provider() == "ollama":
        return os.environ.get("OLLAMA_MODEL") or OLLAMA_MODEL
    return os.environ.get("NVIDIA_MODEL") or DEFAULT_MODEL


def base_url() -> str:
    if provider() == "ollama":
        return _ollama_url() + "/v1"
    return os.environ.get("NVIDIA_BASE_URL", NVIDIA_URL).rstrip("/")


def _ollama_url() -> str:
    return os.environ.get("OLLAMA_URL", OLLAMA_URL).rstrip("/")


def _headers() -> dict:
    if provider() == "ollama":
        return {"Authorization": "Bearer ollama", "Accept": "application/json"}
    key = os.environ.get("NVIDIA_API_KEY", "").strip()
    if not key:
        raise _error(
            "NVIDIA_API_KEY is not set: get a free key at build.nvidia.com and put it in .env", retryable=False
        )
    return {"Authorization": f"Bearer {key}", "Accept": "application/json"}


def _timeout(quick: bool = False) -> float:
    if quick:
        return QUICK_TIMEOUT_SECONDS[provider()]
    return float(os.environ.get("LLM_TIMEOUT", DEFAULT_TIMEOUT_SECONDS))


def _no_model() -> bool:
    """The hosted demo answers from recorded data unless an NVIDIA key is configured there."""
    return os.environ.get("PROVEIT_DEMO") == "1" and not os.environ.get("NVIDIA_API_KEY")


def _no_think(text: str) -> str:
    """Qwen3's switch for answering without a reasoning block (faster on a local CPU)."""
    name = model_name().lower()
    return text + " /no_think" if "qwen3" in name and "instruct" not in name else text


def _strip_reasoning(text: str) -> str:
    """Drop <think>...</think> blocks and ``` fences some models add around JSON."""
    text = re.sub(r"<think>.*?</think>", "", text or "", flags=re.S).strip()
    m = re.match(r"^```(?:json)?\s*(.*?)\s*```$", text, flags=re.S)
    return m.group(1) if m else text


# ---- pacing, retries and health ----------------------------------------------------


class _RateLimiter:
    """Client-side pacing for the shared free tier: at most ``LLM_RPM`` requests in any 60 s window and
    ``LLM_MAX_CONCURRENCY`` in flight, so a run spreads its calls instead of tripping HTTP 429."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._times: list[float] = []
        concurrency = int(os.environ.get("LLM_MAX_CONCURRENCY", DEFAULT_MAX_CONCURRENCY))
        self._sem = threading.BoundedSemaphore(max(1, concurrency))

    def __enter__(self) -> _RateLimiter:
        self._sem.acquire()
        rpm = max(1, int(os.environ.get("LLM_RPM", DEFAULT_RPM)))
        while True:
            with self._lock:
                now = time.time()
                self._times = [t for t in self._times if now - t < RATE_WINDOW_SECONDS]
                if len(self._times) < rpm:
                    self._times.append(now)
                    return self
                wait = RATE_WINDOW_SECONDS - (now - self._times[0]) + RATE_SLACK_SECONDS
            time.sleep(min(wait, RATE_POLL_CAP_SECONDS))

    def __exit__(self, *exc: object) -> None:
        self._sem.release()


_limiter = _RateLimiter()


def _backoff(attempt: int, r: httpx.Response | None) -> float:
    """Exponential back-off (3, 6, 12, 20, 20 s: about a minute in all), honouring Retry-After."""
    if r is not None:
        with contextlib.suppress(ValueError):
            return min(RETRY_AFTER_CAP_SECONDS, float(r.headers.get("retry-after", "")))
    return min(BACKOFF_CAP_SECONDS, BACKOFF_BASE_SECONDS * 2**attempt)


_health = {"state": "ready", "at": 0.0}


def _note(state: str) -> None:
    """Remember how the last real call went, so the console can say "busy" or "not answering" honestly."""
    _health.update(state=state, at=time.time())


def _health_state(status_code: int) -> str:
    if status_code == httpx.codes.OK:
        return "ready"
    return "busy" if status_code == httpx.codes.TOO_MANY_REQUESTS else "unreachable"


def _unreachable(e: httpx.HTTPError) -> LLMError:
    return _error(f"{provider()} model API unreachable: {e}", retryable=isinstance(e, TRANSIENT_ERRORS))


def _drop_optional_field(body: dict) -> bool:
    """Remove the next optional request field after an HTTP 400. False when none is left to drop."""
    dropped = next((f for f in OPTIONAL_FIELDS if f in body), None)
    if dropped is None:
        return False
    body.pop(dropped)
    return True


# ---- requests ----------------------------------------------------------------------


def _post(body: dict, quick: bool = False) -> httpx.Response:
    """POST a chat completion, retrying busy and unreachable servers (never for a quick guard check)."""
    status_retries = 0 if quick else MAX_STATUS_RETRIES
    transport_retries = 0 if quick else MAX_TRANSPORT_RETRIES
    retries = 0
    r = None
    for _ in range(MAX_POST_ATTEMPTS):
        try:
            with _limiter:
                r = httpx.post(f"{base_url()}/chat/completions", json=body, headers=_headers(), timeout=_timeout(quick))
        except TRANSIENT_ERRORS as e:
            _note("unreachable")
            if retries >= transport_retries:
                raise _unreachable(e) from e
            time.sleep(_backoff(retries, None))
            retries += 1
            continue
        except httpx.HTTPError as e:
            raise _unreachable(e) from e
        if r.status_code == httpx.codes.BAD_REQUEST:
            if _drop_optional_field(body):
                continue
            return r
        if r.status_code in RETRY_STATUSES and retries < status_retries:
            _note(_health_state(r.status_code))
            time.sleep(_backoff(retries, r))
            retries += 1
            continue
        _note(_health_state(r.status_code))
        return r
    return r


def _json_body(system: str, user: str, schema: dict, num_predict: int) -> dict:
    return {
        "model": model_name(),
        "messages": [
            {
                "role": "system",
                "content": system + "\n\nReturn only a JSON object matching this JSON "
                "schema, with no other text:\n" + json.dumps(schema),
            },
            {"role": "user", "content": _no_think(user)},
        ],
        "temperature": 0,
        "seed": SEED,
        "max_tokens": max(num_predict, MIN_JSON_TOKENS) * JSON_TOKEN_HEADROOM,
        "stream": False,
        "response_format": {"type": "json_schema", "json_schema": {"name": "output", "schema": schema}},
        "chat_template_kwargs": {"enable_thinking": False},
    }


def _complete(system: str, user: str, schema: dict, num_predict: int, quick: bool = False) -> tuple[str, int, int]:
    if _no_model():
        raise _error("no model in the hosted demo", retryable=False)
    r = _post(_json_body(system, user, schema, num_predict), quick)
    if r.status_code != httpx.codes.OK:
        raise _error(
            f"{provider()} model API returned {r.status_code}: {r.text[:200]}",
            retryable=r.status_code in RETRY_STATUSES,
        )
    data = r.json()
    usage = data.get("usage") or {}
    content = data["choices"][0]["message"].get("content") or ""
    return _strip_reasoning(content), int(usage.get("prompt_tokens", 0)), int(usage.get("completion_tokens", 0))


def set_backend(fn: Backend | None) -> None:
    """Install a fake backend. Only allowed under PROVEIT_ENV=test (tests/ fixtures)."""
    global _backend
    if fn is not None and os.environ.get("PROVEIT_ENV") != "test":
        raise RuntimeError("fake LLM backends are only allowed in tests")
    _backend = fn


def load_prompt(name: str) -> str:
    return (PROMPTS / f"{name}.md").read_text(encoding="utf-8")


def fill(template: str, **values: object) -> str:
    """Replace each ``{{name}}`` in ``template`` (non-string values are inserted as JSON)."""
    out = template
    for k, v in values.items():
        out = out.replace("{{" + k + "}}", v if isinstance(v, str) else json.dumps(v, ensure_ascii=False))
    return out


# ---- usage accounting --------------------------------------------------------------


def _empty_usage() -> dict:
    return {"calls": 0, "tokens_in": 0, "tokens_out": 0, "seconds": 0.0}


def usage(run_id: str) -> dict:
    with _usage_lock:
        return dict(_usage.get(run_id, _empty_usage()))


def _add_usage(run_id: str | None, tin: int, tout: int, secs: float) -> None:
    if not run_id:
        return
    with _usage_lock:
        u = _usage.setdefault(run_id, _empty_usage())
        u["calls"] += 1
        u["tokens_in"] += tin
        u["tokens_out"] += tout
        u["seconds"] = round(u["seconds"] + secs, 2)


def estimate_tokens(text: str) -> int:
    return max(1, len(text) // CHARS_PER_TOKEN)


# ---- public calls ------------------------------------------------------------------


def chat_json(
    schema_model: type[T],
    system: str,
    user: str,
    *,
    run_id: str | None = None,
    agent: str = "",
    num_predict: int = 400,
    quick: bool = False,
) -> tuple[T, dict]:
    """Ask the model for JSON matching ``schema_model``; validate; retry once."""
    schema = schema_model.model_json_schema()
    last_err = None
    meta = {"model": model_name(), "tokens_in": 0, "tokens_out": 0, "seconds": 0.0, "attempts": 0}
    for attempt in range(JSON_ATTEMPTS):
        t0 = time.time()
        if _backend is not None:
            raw = _backend(system, user, schema, agent)
            tin, tout = estimate_tokens(system + user), estimate_tokens(raw)
        else:
            prompt = user if attempt == 0 else user + "\n\nReturn ONLY valid JSON matching the schema."
            raw, tin, tout = _complete(system, prompt, schema, num_predict, quick)
        secs = time.time() - t0
        meta["tokens_in"] += tin
        meta["tokens_out"] += tout
        meta["seconds"] = round(meta["seconds"] + secs, 2)
        meta["attempts"] = attempt + 1
        _add_usage(run_id, tin, tout, secs)
        try:
            return schema_model.model_validate_json(raw), meta
        except ValidationError as e:
            last_err = e
    raise _error(f"{agent}: invalid JSON after retry: {str(last_err)[:300]}", retryable=False)


def chat_stream(
    system: str, messages: list[dict], *, run_id: str | None = None, agent: str = "assistant", num_predict: int = 200
) -> Iterator[str]:
    """Plain-text streaming chat (the spoken assistant). Yields text chunks; thinking is not spoken."""
    t0 = time.time()
    if _backend is not None:
        raw = _backend(system, messages[-1]["content"] if messages else "", {}, agent)
        with contextlib.suppress(ValueError, AttributeError):
            raw = json.loads(raw).get("answer", raw)
        _add_usage(run_id, estimate_tokens(system), estimate_tokens(raw), time.time() - t0)
        yield raw
        return
    if _no_model():
        raise _error("no model in the hosted demo", retryable=False)
    body = _stream_body(system, messages, num_predict)
    tokens = {"prompt_tokens": 0, "completion_tokens": 0}
    try:
        yield from _without_reasoning(_stream_with_retries(body, tokens))
    except httpx.HTTPError as e:
        raise _unreachable(e) from e
    finally:
        _add_usage(run_id, tokens["prompt_tokens"], tokens["completion_tokens"], time.time() - t0)


def _stream_body(system: str, messages: list[dict], num_predict: int) -> dict:
    if messages and messages[-1].get("role") == "user":
        messages = messages[:-1] + [{**messages[-1], "content": _no_think(messages[-1]["content"])}]
    return {
        "model": model_name(),
        "messages": [{"role": "system", "content": system}] + messages,
        "stream": True,
        "temperature": STREAM_TEMPERATURE,
        "max_tokens": num_predict * STREAM_TOKEN_HEADROOM,
        "stream_options": {"include_usage": True},
        "chat_template_kwargs": {"enable_thinking": False},
    }


def _stream_with_retries(body: dict, tokens: dict) -> Iterator[str]:
    """Raw content chunks of one streamed answer, retrying busy servers before the first chunk."""
    for attempt in range(STREAM_ATTEMPTS):
        with (
            _limiter,
            httpx.stream(
                "POST", f"{base_url()}/chat/completions", json=body, headers=_headers(), timeout=_timeout()
            ) as r,
        ):
            if r.status_code == httpx.codes.BAD_REQUEST and "chat_template_kwargs" in body:
                body.pop("chat_template_kwargs")
                continue
            if r.status_code in RETRY_STATUSES and attempt < STREAM_ATTEMPTS - 1:
                r.read()
                time.sleep(_backoff(attempt, r))
                continue
            if r.status_code != httpx.codes.OK:
                r.read()
                raise _error(
                    f"NVIDIA API returned {r.status_code}: {r.text[:160]}", retryable=r.status_code in RETRY_STATUSES
                )
            yield from _sse_content(r, tokens)
            return


def _sse_content(r: httpx.Response, tokens: dict) -> Iterator[str]:
    """Content deltas of a server-sent-events response; records the token usage it reports."""
    for line in r.iter_lines():
        if not line.startswith("data:"):
            continue
        payload = line.removeprefix("data:").strip()
        if payload == "[DONE]":
            return
        event = json.loads(payload)
        if event.get("usage"):
            tokens["prompt_tokens"] = int(event["usage"].get("prompt_tokens", 0))
            tokens["completion_tokens"] = int(event["usage"].get("completion_tokens", 0))
        for choice in event.get("choices") or []:
            yield (choice.get("delta") or {}).get("content") or ""


def _without_reasoning(chunks: Iterator[str]) -> Iterator[str]:
    """Drop everything between <think> and </think>, and empty chunks."""
    in_think = False
    for chunk in chunks:
        if "<think>" in chunk:
            in_think = True
        if in_think:
            if "</think>" not in chunk:
                continue
            in_think = False
            chunk = chunk.split("</think>", 1)[1]
        if chunk:
            yield chunk


def agent_call(
    run_id: str,
    agent: str,
    action: str,
    schema_model: type[T],
    user: str,
    *,
    num_predict: int = 400,
    sources: list[str] | None = None,
    prompt: str | None = None,
) -> T:
    """One logged agent call: prompts/<prompt or agent>.md as the system prompt."""
    try:
        obj, meta = chat_json(
            schema_model, load_prompt(prompt or agent), user, run_id=run_id, agent=agent, num_predict=num_predict
        )
    except LLMError as e:
        log_action(run_id, agent, f"{action}_failed", sources=sources, model=model_name(), cost=0, error=str(e)[:200])
        raise
    log_action(
        run_id,
        agent,
        action,
        sources=sources,
        model=meta["model"],
        cost=0,
        tokens_in=meta["tokens_in"],
        tokens_out=meta["tokens_out"],
        seconds=meta["seconds"],
    )
    return obj


# ---- status for the console --------------------------------------------------------


def status() -> dict:
    """Model readiness for the UI: ready / missing key / not attached (demo)."""
    if _backend is not None:
        return {"state": "ready", "model": model_name()}
    if _no_model():
        return {"state": "not attached in this demo", "model": model_name()}
    if provider() == "ollama":
        return _ollama_status()
    if not os.environ.get("NVIDIA_API_KEY"):
        return {"state": "missing NVIDIA_API_KEY", "model": model_name(), "provider": "nvidia"}
    # Based on the most recent real call (no extra requests): busy or unreachable for a while after a failure.
    state = _health["state"] if time.time() - _health["at"] < HEALTH_MEMORY_SECONDS else "ready"
    return {"state": state, "model": model_name(), "provider": "NVIDIA build (hosted, free tier)"}


def _ollama_status() -> dict:
    """Local model: ready once Ollama answers and the model has finished downloading."""
    base = {"model": model_name(), "provider": "Ollama (local, open weights)"}
    try:
        r = httpx.get(_ollama_url() + "/api/tags", timeout=OLLAMA_STATUS_TIMEOUT_SECONDS)
        names = {m.get("name", "") for m in r.json().get("models", [])}
    except (httpx.HTTPError, ValueError):
        return {"state": "unreachable", **base}
    want = model_name()
    have = want in names or f"{want}:latest" in names
    return {"state": "ready" if have else "downloading the local model", **base}
