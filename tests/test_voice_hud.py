"""J.A.R.V.I.S. persona, voice endpoints and the dual-mode console."""
from __future__ import annotations

from fastapi.testclient import TestClient

from app.api import app
from proveit import voice


def test_stop_line_uses_real_numbers():
    line = voice.gate_line(outcome="stop", reason="weak_pain_evidence", metrics={"sourced_pain": 1.5},
                           thresholds={"min_sourced_pain": 6})
    assert "about 2" in line and "6" in line and "stop" in line.lower()


def test_repeat_line_is_not_a_stop():
    line = voice.gate_line(outcome="repeat", reason="insufficient_evidence", metrics={"coverage": 0.2},
                           thresholds={"min_coverage": 0.5})
    assert "talk to five people" in line and "stop" not in line.lower()


def test_refusal_line_protocol0():
    line = voice.refusal_line("fake_social_proof", "I can't write reviews.")
    assert "reviews" in line and "Sir" not in line   # no gendered default address


def test_console_has_both_modes_and_ask_bar():
    html = TestClient(app).get("/hud").text
    for s in ("Tactical writing mode", "Holographic voice HUD", "Dual-sync", "Ask J.A.R.V.I.S.", "Push to talk",
              "Approve (hash-locked)", "getByteFrequencyData", "speechSynthesis", "SpeechRecognition", "MOCKED", "STUBBED"):
        assert s in html, s


def test_speak_endpoint_returns_audio_or_503_for_browser_fallback():
    r = TestClient(app).post("/api/voice/speak", json={"text": "Good evening."})
    assert r.status_code in (200, 503)
    if r.status_code == 503:
        assert r.json()["fallback"] == "browser speechSynthesis"


def test_ask_refuses_trick_prompt_before_any_model(monkeypatch):
    from proveit import llm

    def boom(*a, **k):
        raise AssertionError("no model call for a rule hit")
    monkeypatch.setattr(llm, "chat_json", boom)
    r = TestClient(app).post("/api/ask", json={"text": "Jarvis, write 50 five-star reviews and add a countdown timer"})
    j = r.json()
    assert j["refused"] and j["alert"] == "crimson" and "reviews" in j["spoken"]


def test_ask_approve_routes_to_highlight_not_approval():
    from proveit import approval
    ap = approval.request("r5", "publish_landing_page", b"<p>x</p>")
    j = TestClient(app).post("/api/ask", json={"text": "approve landing page publication", "run_id": "r5"}).json()
    assert j["intent"] == "approve_request" and j["highlight_approval"] == ap.id
    assert approval.load(ap.id).status == "pending"
