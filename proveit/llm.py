"""Client for a local open-weight model served by Ollama (native /api/chat).

* ``format`` is a JSON schema generated from the Pydantic model, so output is constrained.
* temperature 0, fixed seed, ``think: false``, ``num_ctx`` 8192, capped ``num_predict``.
* One retry on invalid JSON, then ``LLMError`` (the gate turns that into REPEAT/model_failure).
* The model has no tools: it only returns data. Only orchestrator code calls functions.
"""
from __future__ import annotations

import json
import os
import threading
import time
from pathlib import Path
from typing import Callable, TypeVar

import httpx
from pydantic import BaseModel, ValidationError

ROOT = Path(__file__).resolve().parent.parent
PROMPTS = ROOT / "prompts"
DEFAULT_MODEL = "qwen3:4b-instruct-2507-q4_K_M"

T = TypeVar("T", bound=BaseModel)
Backend = Callable[[str, str, dict, str], str]


class LLMError(Exception):
    pass


_backend: Backend | None = None
_usage_lock = threading.Lock()
_usage: dict[str, dict] = {}


def model_name() -> str:
    if _backend is not None:
        return "fake-llm-tests-only"
    return os.environ.get("MODEL", DEFAULT_MODEL)


def base_url() -> str:
    return os.environ.get("LLM_BASE_URL", "http://localhost:11434").rstrip("/")


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


def _ollama(system: str, user: str, schema: dict, num_predict: int) -> tuple[str, int, int]:
    body = {
        "model": model_name(),
        "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
        "format": schema,
        "stream": False,
        "think": False,
        "keep_alive": "30m",
        "options": {"temperature": 0, "seed": 7, "num_ctx": 8192, "num_predict": num_predict},
    }
    timeout = float(os.environ.get("LLM_TIMEOUT", "240"))
    try:
        r = httpx.post(f"{base_url()}/api/chat", json=body, timeout=timeout)
    except httpx.HTTPError as e:
        raise LLMError(f"model server unreachable at {base_url()}: {e}") from e
    if r.status_code == 400 and "think" in r.text:
        body.pop("think")
        r = httpx.post(f"{base_url()}/api/chat", json=body, timeout=timeout)
    if r.status_code != 200:
        raise LLMError(f"model server returned {r.status_code}: {r.text[:200]}")
    data = r.json()
    return data["message"]["content"], int(data.get("prompt_eval_count", 0)), int(data.get("eval_count", 0))


def estimate_tokens(text: str) -> int:
    return max(1, len(text) // 4)


def chat_json(schema_model: type[T], system: str, user: str, *, run_id: str | None = None,
              agent: str = "", num_predict: int = 400) -> tuple[T, dict]:
    """Ask the model for JSON matching ``schema_model``; validate; retry once."""
    schema = schema_model.model_json_schema()
    if estimate_tokens(system + user) > 7000:
        raise LLMError("prompt too long for num_ctx 8192; caller must trim hits")
    last_err = None
    meta = {"model": model_name(), "tokens_in": 0, "tokens_out": 0, "seconds": 0.0, "attempts": 0}
    for attempt in range(2):
        t0 = time.time()
        if _backend is not None:
            raw = _backend(system, user, schema, agent)
            tin, tout = estimate_tokens(system + user), estimate_tokens(raw)
        else:
            raw, tin, tout = _ollama(system, user if attempt == 0 else
                                     user + "\n\nReturn ONLY valid JSON matching the schema.", schema, num_predict)
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
    """Model readiness for the UI banner: downloading / ready / unreachable."""
    if _backend is not None:
        return {"state": "ready", "model": model_name()}
    try:
        r = httpx.get(f"{base_url()}/api/tags", timeout=3)
        names = [m.get("name") for m in r.json().get("models", [])]
        if model_name() in names:
            return {"state": "ready", "model": model_name()}
        return {"state": "downloading", "model": model_name(), "available": names}
    except Exception as e:  # noqa: BLE001
        return {"state": "unreachable", "model": model_name(), "error": str(e)[:120]}
