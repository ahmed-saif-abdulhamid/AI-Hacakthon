"""The optional NVIDIA provider: request shape, JSON validation and the missing-key error (no network)."""

from __future__ import annotations

import json

import httpx
import pytest
from pydantic import BaseModel

from proveit import llm, metrics


class Out(BaseModel):
    answer: str


class FakeResp:
    def __init__(self, status: int, payload: dict):
        self.status_code, self._p, self.text = status, payload, json.dumps(payload)

    def json(self):
        return self._p


def test_nvidia_provider_sends_schema_and_parses_json(monkeypatch):
    monkeypatch.setenv("NVIDIA_API_KEY", "test-key-not-real")
    seen = {}

    def fake_post(url, json=None, headers=None, timeout=None):
        seen.update(url=url, body=json, headers=headers)
        content = '<think>plan</think>```json\n{"answer": "ok"}\n```'
        return FakeResp(
            200,
            {"choices": [{"message": {"content": content}}], "usage": {"prompt_tokens": 10, "completion_tokens": 3}},
        )

    monkeypatch.setattr(httpx, "post", fake_post)
    out, meta = llm.chat_json(Out, "system", "user")
    assert out.answer == "ok" and meta["tokens_in"] == 10
    assert seen["url"].endswith("/chat/completions")
    assert seen["body"]["response_format"]["json_schema"]["schema"]["properties"]["answer"]
    assert seen["body"]["chat_template_kwargs"] == {"enable_thinking": False}
    assert seen["headers"]["Authorization"] == "Bearer test-key-not-real"
    assert llm.model_name() == llm.DEFAULT_MODEL


def test_nvidia_without_key_fails_clearly(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "nvidia")
    monkeypatch.delenv("NVIDIA_API_KEY", raising=False)
    with pytest.raises(llm.LLMError, match="NVIDIA_API_KEY"):
        llm.chat_json(Out, "s", "u")
    assert llm.status()["state"] == "missing NVIDIA_API_KEY"


def test_option_rejected_with_400_is_dropped_and_retried(monkeypatch):
    monkeypatch.setenv("NVIDIA_API_KEY", "test-key-not-real")
    calls = []

    def fake_post(url, json=None, headers=None, timeout=None):
        calls.append(dict(json))
        if "chat_template_kwargs" in json:
            return FakeResp(400, {"error": "unknown field"})
        return FakeResp(200, {"choices": [{"message": {"content": '{"answer": "fine"}'}}], "usage": {}})

    monkeypatch.setattr(httpx, "post", fake_post)
    out, _ = llm.chat_json(Out, "s", "u")
    assert out.answer == "fine" and len(calls) == 2 and "response_format" in calls[1]


def test_provider_defaults_to_the_local_model_without_a_key(monkeypatch):
    monkeypatch.delenv("LLM_PROVIDER", raising=False)
    monkeypatch.delenv("NVIDIA_API_KEY", raising=False)
    assert llm.provider() == "ollama" and llm.base_url() == "http://localhost:11434/v1"
    assert llm.model_name() == llm.OLLAMA_MODEL and "Authorization" in llm._headers()
    monkeypatch.setenv("NVIDIA_API_KEY", "test-key-not-real")
    assert llm.provider() == "nvidia" and llm.base_url().startswith("https://integrate.api.nvidia.com")
    monkeypatch.setenv("LLM_PROVIDER", "ollama")
    assert llm.provider() == "ollama"


def test_qwen3_is_asked_to_answer_without_a_reasoning_block(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "ollama")
    monkeypatch.setenv("OLLAMA_MODEL", "qwen3:8b")
    assert llm._no_think("hello").endswith("/no_think")
    monkeypatch.setenv("OLLAMA_MODEL", "qwen3:4b-instruct-2507-q4_K_M")  # instruct: no reasoning block anyway
    assert llm._no_think("hello") == "hello"
    monkeypatch.setenv("OLLAMA_MODEL", "llama3.2")
    assert llm._no_think("hello") == "hello"


@pytest.mark.parametrize(("status", "retryable"), [(429, True), (503, True), (401, False), (404, False)])
def test_llm_error_says_whether_a_retry_can_help(monkeypatch, status, retryable):
    monkeypatch.setenv("NVIDIA_API_KEY", "test-key-not-real")
    metrics.reset()
    monkeypatch.setattr(httpx, "post", lambda *a, **k: FakeResp(status, {"error": "nope"}))
    with pytest.raises(llm.LLMError, match=f"returned {status}") as err:
        llm.chat_json(Out, "s", "u", quick=True)
    assert err.value.retryable is retryable
    assert metrics.value("llm_call_failed", retryable=retryable) == 1


def test_unreachable_model_is_retryable(monkeypatch):
    monkeypatch.setenv("NVIDIA_API_KEY", "test-key-not-real")

    def timeout(*a, **k):
        raise httpx.ConnectTimeout("timed out")

    monkeypatch.setattr(httpx, "post", timeout)
    with pytest.raises(llm.LLMError, match="unreachable") as err:
        llm.chat_json(Out, "s", "u", quick=True)
    assert err.value.retryable
