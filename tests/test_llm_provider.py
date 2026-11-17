"""The optional NVIDIA provider: request shape, JSON validation and the missing-key error (no network)."""
from __future__ import annotations

import json

import httpx
import pytest
from pydantic import BaseModel

from proveit import llm


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
        return FakeResp(200, {"choices": [{"message": {"content": content}}],
                              "usage": {"prompt_tokens": 10, "completion_tokens": 3}})
    monkeypatch.setattr(httpx, "post", fake_post)
    out, meta = llm.chat_json(Out, "system", "user")
    assert out.answer == "ok" and meta["tokens_in"] == 10
    assert seen["url"].endswith("/chat/completions")
    assert seen["body"]["response_format"]["json_schema"]["schema"]["properties"]["answer"]
    assert seen["body"]["chat_template_kwargs"] == {"enable_thinking": False}
    assert seen["headers"]["Authorization"] == "Bearer test-key-not-real"
    assert llm.model_name() == llm.DEFAULT_MODEL


def test_nvidia_without_key_fails_clearly(monkeypatch):
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


def test_no_local_model_is_used():
    assert llm.provider() == "nvidia" and llm.base_url().startswith("https://integrate.api.nvidia.com")
