"""Test setup: PROVEIT_ENV=test, a temp database and temp run/output dirs per test.
Tests never touch the committed root files except to read them."""
from __future__ import annotations

import json
import os
import sys
from datetime import datetime
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
os.environ["PROVEIT_ENV"] = "test"

from proveit import llm  # noqa: E402
from proveit.models import Hit, SourceCall  # noqa: E402
from sources.base import split_sentences  # noqa: E402

FIX = Path(__file__).parent / "fixtures"


@pytest.fixture(autouse=True)
def isolated(tmp_path, monkeypatch):
    monkeypatch.setenv("PROVEIT_ENV", "test")
    monkeypatch.setenv("PROVEIT_DB", str(tmp_path / "test.db"))
    monkeypatch.setenv("PROVEIT_RUNS", str(tmp_path / "runs"))
    monkeypatch.setenv("PROVEIT_OUTPUTS", str(tmp_path / "outputs"))
    monkeypatch.setenv("PROVEIT_DATA", str(tmp_path / "data"))
    monkeypatch.setenv("SECRET_KEY", "test-secret")
    yield
    llm.set_backend(None)


@pytest.fixture
def fake_llm():
    sys.path.insert(0, str(FIX))
    import fake_llm as f  # noqa: PLC0415
    llm.set_backend(f.backend)
    yield f
    llm.set_backend(None)


def load_fixture(name: str) -> dict:
    return json.loads((FIX / name).read_text(encoding="utf-8"))


def fixture_gather(name: str):
    """Replace the network sources with a recorded fixture (offline, deterministic)."""
    data = load_fixture(name)

    def gather(run, variant, caps, limits, broaden=False):
        hits, calls, by_call = [], [], {}
        for i, c in enumerate(data["calls"]):
            hs = [Hit(id="", source=h["source"], url=h["url"], title=h["title"], text=h["text"],
                      sentences=split_sentences(h["text"]),
                      published_at=datetime.fromisoformat(h["published_at"]), engagement=h["engagement"])
                  for h in c["hits"]]
            calls.append(SourceCall(source=c["source"], query=c["query"], url="fixture", ok=c["ok"],
                                    n_hits=len(hs), pain_capable=c["pain_capable"], error=c.get("error")))
            by_call[i] = hs
            hits.extend(hs)
        return hits, calls, by_call, None
    return gather, data


@pytest.fixture
def offline_sources(monkeypatch):
    """Patch sources + live re-fetch. Pages 'contain' exactly the fixture text."""
    from proveit import orchestrator, verifier

    def use(name: str):
        gather, data = fixture_gather(name)
        pages = {h["url"]: h["text"] for c in data["calls"] for h in c["hits"]}
        monkeypatch.setattr(orchestrator, "gather", gather)
        monkeypatch.setattr(orchestrator, "score_alternatives", lambda run, variants, months: [
            {"n": v.n, "title": v.title, "comments_checked": 20, "on_topic": 9 - v.n, "complaints": 4 - v.n,
             "fit": 0.5, "errors": 0, "signal": 10 - v.n, "chosen": v.n == 1} for v in variants])
        monkeypatch.setattr(verifier, "_fetch", lambda url, timeout: pages.get(url))
        return data
    return use
