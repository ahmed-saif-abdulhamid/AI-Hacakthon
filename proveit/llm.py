"""Client for open-weight models through an OpenAI-compatible API. Two providers:

* ``ollama`` (the Docker default): a local model served by Ollama, downloaded on first start by
  ``docker compose up``. No key, no account, nothing leaves the computer. ``OLLAMA_MODEL``
  (default ``qwen3:8b``), ``OLLAMA_URL`` (default ``http://localhost:11434``).
* ``nvidia``: open-weight NVIDIA Nemotron on build.nvidia.com's free developer tier
  (``NVIDIA_API_KEY``, roughly 40 requests a minute). Override the model with ``NVIDIA_MODEL``.

``LLM_PROVIDER`` picks one; unset, a configured NVIDIA key selects ``nvidia``, otherwise ``ollama``.
* Structured calls send the Pydantic JSON schema as ``response_format`` (constrained output),
  temperature 0 and a fixed seed; one retry on invalid JSON, then ``LLMError`` (the gate turns
  that into REPEAT/model_failure).
* The model has no tools: it only returns data. Only orchestrator code calls functions.
"""
from __future__ import annotations

import json
import os
import re
import threading
import time
from pathlib import Path
from typing import Callable, TypeVar

import httpx
from pydantic import BaseModel, ValidationError

ROOT = Path(__file__).resolve().parent.parent
PROMPTS = ROOT / "prompts"
NVIDIA_URL = "https://integrate.api.nvidia.com/v1"
DEFAULT_MODEL = "nvidia/nemotron-3-ultra-550b-a55b"
OLLAMA_URL = "http://localhost:11434"
OLLAMA_MODEL = "qwen3:8b"

T = TypeVar("T", bound=BaseModel)
Backend = Callable[[str, str, dict, str], str]


class LLMError(Exception):
    pass


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


def provider() -> str:
    chosen = os.environ.get("LLM_PROVIDER", "").strip().lower()
    if chosen in ("ollama", "nvidia"):
        return chosen
    return "nvidia" if os.environ.get("NVIDIA_API_KEY", "").strip() else "ollama"


def model_name() -> str:
    if _backend is not None:
        return "fake-llm-tests-only"
    if provider() == "ollama":
        return os.environ.get("OLLAMA_MODEL") or OLLAMA_MODEL
    return os.environ.get("NVIDIA_MODEL") or DEFAULT_MODEL


def base_url() -> str:
    if provider() == "ollama":
        return os.environ.get("OLLAMA_URL", OLLAMA_URL).rstrip("/") + "/v1"
    return os.environ.get("NVIDIA_BASE_URL", NVIDIA_URL).rstrip("/")


def _headers() -> dict:
    if provider() == "ollama":
        return {"Authorization": "Bearer ollama", "Accept": "application/json"}
    key = os.environ.get("NVIDIA_API_KEY", "").strip()
    if not key:
        raise LLMError("NVIDIA_API_KEY is not set: get a free key at build.nvidia.com and put it in .env")
    return {"Authorization": f"Bearer {key}", "Accept": "application/json"}


def _timeout() -> float:
    return float(os.environ.get("LLM_TIMEOUT", "120"))


def _quick_timeout() -> float:
    """Guard checks wait 10 s for the hosted model; a local model on a CPU needs longer."""
    return 45.0 if provider() == "ollama" else 10.0


def _no_model() -> bool:
    """The hosted demo answers from recorded data unless an NVIDIA key is configured there."""
    return os.environ.get("PROVEIT_DEMO") == "1" and not os.environ.get("NVIDIA_API_KEY")


def _no_think(text: str) -> str:
    """Qwen3's switch for answering without a reasoning block (faster on a local CPU)."""
    return text + " /no_think" if "qwen3" in model_name().lower() else text


def _strip_reasoning(text: str) -> str:
    """Drop <think>...</think> blocks and ``` fences some models add around JSON."""
    text = re.sub(r"<think>.*?</think>", "", text or "", flags=re.S).strip()
    m = re.match(r"^```(?:json)?\s*(.*?)\s*```$", text, flags=re.S)
    return m.group(1) if m else text


# Request options tried in order: drop the ones a model rejects with HTTP 400.
OPTIONAL_FIELDS = ("chat_template_kwargs", "response_format")


RETRY_STATUSES = (429, 500, 502, 503, 504)


class _RateLimiter:
    """Client-side pacing for the shared free tier: at most ``LLM_RPM`` requests in any 60 s window and
    ``LLM_MAX_CONCURRENCY`` in flight, so a run spreads its calls instead of tripping HTTP 429."""

    def __init__(self):
        self._lock = threading.Lock()
        self._times: list[float] = []
        self._sem = threading.BoundedSemaphore(max(1, int(os.environ.get("LLM_MAX_CONCURRENCY", "2"))))

    def __enter__(self):
        self._sem.acquire()
        rpm = max(1, int(os.environ.get("LLM_RPM", "30")))
        while True:
            with self._lock:
                now = time.time()
                self._times = [t for t in self._times if now - t < 60]
                if len(self._times) < rpm:
                    self._times.append(now)
                    return self
                wait = 60 - (now - self._times[0]) + 0.05
            time.sleep(min(wait, 5))

    def __exit__(self, *exc):
        self._sem.release()


_limiter = _RateLimiter()


def _backoff(attempt: int, r: httpx.Response | None) -> float:
    """Exponential back-off (3, 6, 12, 20, 20 s: about a minute in all), honouring Retry-After."""
    if r is not None:
        try:
            return min(30.0, float(r.headers.get("retry-after", "")))
        except ValueError:
            pass
    return min(20.0, 3.0 * 2 ** attempt)


_health = {"state": "ready", "at": 0.0}


def _note(state: str) -> None:
    """Remember how the last real call went, so the console can say "busy" or "not answering" honestly."""
    _health.update(state=state, at=time.time())


def _post(body: dict, quick: bool = False) -> httpx.Response:
    r = None
    retries = 0
    max_retries = 0 if quick else 5
    for _ in range(10):
        try:
            with _limiter:
                r = httpx.post(f"{base_url()}/chat/completions", json=body, headers=_headers(),
                               timeout=_quick_timeout() if quick else _timeout())
        except (httpx.TimeoutException, httpx.NetworkError) as e:
            _note("unreachable")
            if quick or retries >= 2:
                raise LLMError(f"{provider()} model API unreachable: {e}") from e
            time.sleep(_backoff(retries, None))
            retries += 1
            continue
        except httpx.HTTPError as e:
            raise LLMError(f"{provider()} model API unreachable: {e}") from e
        if r.status_code == 400:
            dropped = next((f for f in OPTIONAL_FIELDS if f in body), None)
            if dropped is None:
                return r
            body.pop(dropped)
            continue
        if r.status_code in RETRY_STATUSES and retries < max_retries:   # free-tier rate limit or a transient error
            _note("busy" if r.status_code == 429 else "unreachable")
            time.sleep(_backoff(retries, r))
            retries += 1
            continue
        _note("ready" if r.status_code == 200 else ("busy" if r.status_code == 429 else "unreachable"))
        return r
    return r


def _complete(system: str, user: str, schema: dict, num_predict: int, quick: bool = False) -> tuple[str, int, int]:
    if _no_model():
        raise LLMError("no model in the hosted demo")
    body = {
        "model": model_name(),
        "messages": [{"role": "system", "content": system + "\n\nReturn only a JSON object matching this JSON "
                      "schema, with no other text:\n" + json.dumps(schema)},
                     {"role": "user", "content": _no_think(user)}],
        "temperature": 0, "seed": 7, "max_tokens": max(num_predict, 256) * 2, "stream": False,
        "response_format": {"type": "json_schema", "json_schema": {"name": "output", "schema": schema}},
        "chat_template_kwargs": {"enable_thinking": False},
    }
    r = _post(body, quick)
    if r.status_code != 200:
        raise LLMError(f"{provider()} model API returned {r.status_code}: {r.text[:200]}")
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


def fill(template: str, **values) -> str:
    out = template
    for k, v in values.items():
        out = out.replace("{{" + k + "}}", v if isinstance(v, str) else json.dumps(v, ensure_ascii=False))
    return out


def usage(run_id: str) -> dict:
    with _usage_lock:
        return dict(_usage.get(run_id, {"calls": 0, "tokens_in": 0, "tokens_out": 0, "seconds": 0.0}))


def _add_usage(run_id: str | None, tin: int, tout: int, secs: float) -> None:
    if not run_id:
        return
    with _usage_lock:
        u = _usage.setdefault(run_id, {"calls": 0, "tokens_in": 0, "tokens_out": 0, "seconds": 0.0})
        u["calls"] += 1
        u["tokens_in"] += tin
        u["tokens_out"] += tout
        u["seconds"] = round(u["seconds"] + secs, 2)


def estimate_tokens(text: str) -> int:
    return max(1, len(text) // 4)


def chat_json(schema_model: type[T], system: str, user: str, *, run_id: str | None = None,
              agent: str = "", num_predict: int = 400, quick: bool = False) -> tuple[T, dict]:
    """Ask the model for JSON matching ``schema_model``; validate; retry once."""
    schema = schema_model.model_json_schema()
    last_err = None
    meta = {"model": model_name(), "tokens_in": 0, "tokens_out": 0, "seconds": 0.0, "attempts": 0}
    for attempt in range(2):
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
    raise LLMError(f"{agent}: invalid JSON after retry: {str(last_err)[:300]}")


def chat_stream(system: str, messages: list[dict], *, run_id: str | None = None, agent: str = "assistant",
                num_predict: int = 200):
    """Plain-text streaming chat (the spoken assistant). Yields text chunks; thinking is not spoken."""
    t0 = time.time()
    if _backend is not None:
        raw = _backend(system, messages[-1]["content"] if messages else "", {}, agent)
        try:
            raw = json.loads(raw).get("answer", raw)
        except (ValueError, AttributeError):
            pass
        _add_usage(run_id, estimate_tokens(system), estimate_tokens(raw), time.time() - t0)
        yield raw
        return
    if _no_model():
        raise LLMError("no model in the hosted demo")
    if messages and messages[-1].get("role") == "user":
        messages = messages[:-1] + [{**messages[-1], "content": _no_think(messages[-1]["content"])}]
    body = {"model": model_name(), "messages": [{"role": "system", "content": system}] + messages,
            "stream": True, "temperature": 0.3, "max_tokens": num_predict * 3,
            "stream_options": {"include_usage": True}, "chat_template_kwargs": {"enable_thinking": False}}
    tin = tout = 0
    in_think = False
    try:
        for attempt in range(4):
            with _limiter, httpx.stream("POST", f"{base_url()}/chat/completions", json=body, headers=_headers(),
                                        timeout=_timeout()) as r:
                if r.status_code == 400 and "chat_template_kwargs" in body:
                    body.pop("chat_template_kwargs")
                    continue
                if r.status_code in RETRY_STATUSES and attempt < 3:
                    r.read()
                    time.sleep(_backoff(attempt, r))
                    continue
                if r.status_code != 200:
                    r.read()
                    raise LLMError(f"NVIDIA API returned {r.status_code}: {r.text[:160]}")
                for line in r.iter_lines():
                    if not line.startswith("data:"):
                        continue
                    payload = line[5:].strip()
                    if payload == "[DONE]":
                        break
                    d = json.loads(payload)
                    if d.get("usage"):
                        tin = int(d["usage"].get("prompt_tokens", 0))
                        tout = int(d["usage"].get("completion_tokens", 0))
                    for ch in d.get("choices") or []:
                        chunk = (ch.get("delta") or {}).get("content") or ""
                        if "<think>" in chunk:
                            in_think = True
                        if in_think:
                            if "</think>" not in chunk:
                                continue
                            in_think = False
                            chunk = chunk.split("</think>", 1)[1]
                        if chunk:
                            yield chunk
                return
    except httpx.HTTPError as e:
        raise LLMError(f"{provider()} model API unreachable: {e}") from e
    finally:
        _add_usage(run_id, tin, tout, time.time() - t0)


def agent_call(run_id: str, agent: str, action: str, schema_model: type[T], user: str, *,
               num_predict: int = 400, sources: list[str] | None = None, prompt: str | None = None) -> T:
    """One logged agent call: prompts/<prompt or agent>.md as the system prompt."""
    from .log import log_action
    try:
        obj, meta = chat_json(schema_model, load_prompt(prompt or agent), user, run_id=run_id,
                              agent=agent, num_predict=num_predict)
    except LLMError as e:
        log_action(run_id, agent, f"{action}_failed", sources=sources, model=model_name(), cost=0,
                   error=str(e)[:200])
        raise
    log_action(run_id, agent, action, sources=sources, model=meta["model"], cost=0,
               tokens_in=meta["tokens_in"], tokens_out=meta["tokens_out"], seconds=meta["seconds"])
    return obj


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
    # Based on the most recent real call (no extra requests): busy or unreachable for 90 s after a failure.
    state = _health["state"] if time.time() - _health["at"] < 90 else "ready"
    return {"state": state, "model": model_name(), "provider": "NVIDIA build (hosted, free tier)"}


def _ollama_status() -> dict:
    """Local model: ready once Ollama answers and the model has finished downloading."""
    base = {"model": model_name(), "provider": "Ollama (local, open weights)"}
    try:
        r = httpx.get(os.environ.get("OLLAMA_URL", OLLAMA_URL).rstrip("/") + "/api/tags", timeout=2)
        names = {m.get("name", "") for m in r.json().get("models", [])}
    except (httpx.HTTPError, ValueError):
        return {"state": "unreachable", **base}
    want = model_name()
    have = want in names or f"{want}:latest" in names
    return {"state": "ready" if have else "downloading the local model", **base}
