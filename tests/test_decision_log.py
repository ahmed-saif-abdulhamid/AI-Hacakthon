"""The committed decision_log.json: a JSON array, five required keys on every entry,
byte-identical to runs/promoted/decision_log.json and matching runs/promoted/runs.json."""
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
LOG = ROOT / "decision_log.json"
PROMOTED = ROOT / "runs" / "promoted"


def load():
    return json.loads(LOG.read_text(encoding="utf-8"))


def test_is_array_with_required_keys():
    data = load()
    assert isinstance(data, list) and data
    for e in data:
        for k in ("timestamp", "agent", "action", "sources", "model", "cost", "approved_by"):
            assert k in e, (k, e)
        assert isinstance(e["action"], str) and isinstance(e["sources"], list)
        assert e["model"] is None or isinstance(e["model"], str)
        assert isinstance(e["cost"], (int, float))
        assert e["approved_by"] in (None, "founder")


def test_byte_identical_to_promoted_and_matches_runs_json():
    assert LOG.read_bytes() == (PROMOTED / "decision_log.json").read_bytes()
    meta = json.loads((PROMOTED / "runs.json").read_text(encoding="utf-8"))
    data = load()
    assert len(data) == meta["entries"]
    assert {e["run_id"] for e in data} == {meta["weak"], meta["strong"]}


def test_each_run_starts_with_preregistration():
    data = load()
    first = {}
    for e in data:
        first.setdefault(e["run_id"], e)
    assert all(e["action"] == "preregister_thresholds" and e.get("thresholds_sha256") for e in first.values())


def test_outcomes_canonical_and_weak_run_stops():
    data = load()
    meta = json.loads((PROMOTED / "runs.json").read_text(encoding="utf-8"))
    assert {e["outcome"] for e in data if "outcome" in e} <= {"go", "repeat", "pivot", "stop"}
    weak_gate = [e for e in data if e["run_id"] == meta["weak"] and e["action"] == "evidence_gate"]
    assert weak_gate and weak_gate[-1]["outcome"] == "stop"


def test_gated_actions_carry_founder_approval():
    for e in load():
        if e["action"] in ("publish_landing_page", "open_store", "refund"):
            assert e["approved_by"] == "founder"
