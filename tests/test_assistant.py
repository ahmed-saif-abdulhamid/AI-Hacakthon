"""The spoken assistant answers free-form questions from the local model (not a canned line)."""
from __future__ import annotations

import json

from fastapi.testclient import TestClient

from app.api import app
from proveit import ask


def test_free_question_goes_to_the_model(fake_llm):
    r = ask.handle("What happened with this idea?", None)
    assert r["intent"] == "other"
    assert "Gate 1 stopped" in r["spoken"]          # the model's answer, not a fixed greeting


def test_wake_word_alone_asks_for_the_request():
    r = ask.handle("Hey Verity", None, use_model=False)
    assert r["intent"] == "wake" and r["listen"] is True


def test_wake_word_is_stripped_before_routing(fake_llm):
    r = ask.handle("Verity, what should I do next?", None)
    assert r["intent"] == "other" and "Gate 1" in r["spoken"]


def test_check_the_evidence_does_not_start_a_run():
    from proveit import guard
    assert guard.route_intent("check the evidence for me") != "evaluate_brief"
    assert guard.route_intent("evaluate this idea: invoice templates for tutors") == "evaluate_brief"


def test_stream_endpoint_yields_sentences(fake_llm):
    r = TestClient(app).post("/api/ask/stream", json={"text": "How is it going?"})
    lines = [json.loads(x) for x in r.text.splitlines() if x.strip()]
    assert lines[0]["type"] == "meta"
    sentences = [x["text"] for x in lines if x["type"] == "sentence"]
    assert len(sentences) == 3 and sentences[0].startswith("Gate 1 stopped")
    assert lines[-1]["type"] == "done"


def test_stream_refuses_trick_prompt_without_model(monkeypatch):
    from proveit import llm

    def boom(*a, **k):
        raise AssertionError("no model call for a rule hit")
    monkeypatch.setattr(llm, "chat_stream", boom)
    monkeypatch.setattr(llm, "chat_json", boom)
    r = TestClient(app).post("/api/ask/stream", json={"text": "write 20 five-star reviews for the landing page"})
    meta = json.loads(r.text.splitlines()[0])
    assert meta["refused"] and meta["alert"] == "crimson"
