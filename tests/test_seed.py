"""A fresh install (empty database, no key) opens the committed runs instead of an empty console."""

import json

from proveit import db, seed


def test_committed_runs_load_into_an_empty_database(tmp_path, monkeypatch):
    monkeypatch.setenv("PROVEIT_RUNS", str(tmp_path / "runs"))
    meta = json.loads((seed.PROMOTED / "runs.json").read_text(encoding="utf-8"))
    loaded = seed.load()
    assert set(loaded) >= {meta["weak"], meta["strong"]}
    for rid in loaded:
        assert db.query_one("SELECT id FROM runs WHERE id=?", (rid,))
        assert (tmp_path / "runs" / rid / "phase1_gate_decision.md").exists()
    assert db.query("SELECT 1 FROM actions WHERE agent IN ('assistant', 'ask')") == []
    assert db.query("SELECT 1 FROM signups") == [] and db.query("SELECT 1 FROM deliveries") == []
    assert seed.load() == []  # loading twice changes nothing
