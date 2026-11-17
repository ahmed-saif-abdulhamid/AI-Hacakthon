"""Assistant persona, voice endpoints and the dual-mode console."""
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
    c = TestClient(app)
    html = c.get("/hud").text + c.get("/static/console.js").text
    name = voice.assistant_name()
    for s in ("Tactical writing mode", "Holographic voice HUD", "Dual-sync", f"Ask {name}", "Push to talk",
              "Approve (hash-locked)", "getByteFrequencyData", "speechSynthesis", "SpeechRecognition", "MOCKED", "STUBBED",
              'role="tablist"', 'role="tab"', "aria-live", "Skip to the current idea"):
        assert s in html, s


def test_console_uses_the_assistant_name_and_no_gendered_default():
    html = TestClient(app).get("/hud").text
    assert "J.A.R.V.I.S." in html and "Jarvis" in html and "Sir" not in html


def test_designed_error_page_for_browsers_and_json_for_api():
    c = TestClient(app)
    page = c.get("/nope", headers={"accept": "text/html"})
    assert page.status_code == 404 and "Page not found" in page.text and "<html" in page.text
    api = c.get("/api/runs/nope-run")
    assert api.status_code == 404 and api.json()["ok"] is False


def test_security_headers_present():
    r = TestClient(app).get("/hud")
    assert "frame-ancestors" in r.headers["content-security-policy"]
    assert r.headers["x-content-type-options"] == "nosniff"
    assert "microphone=(self)" in r.headers["permissions-policy"]


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
