"""outputs/: names by phase and step, a STOP gate for the weak run, the payment log,
and every claim SOURCED or ASSUMPTION."""
from __future__ import annotations

import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "outputs"
NAME = re.compile(r"^(phase\d+_(step\d+|gate)_[a-z0-9-]+|payment_test_log)\.(md|json|csv|txt|html)$")


def files():
    return [p for p in OUT.iterdir() if p.is_file() and p.name != ".gitkeep"]


def test_names_and_text_formats():
    fs = files()
    assert fs
    for p in fs:
        assert NAME.match(p.name), p.name
        assert p.stat().st_size < 200_000, p.name


def test_weak_run_recommends_stop():
    text = (OUT / "phase1_gate_decision-weak.md").read_text(encoding="utf-8")
    assert "## Outcome: STOP" in text


def test_payment_log_and_reconciliation_present():
    log = (OUT / "payment_test_log.md").read_text(encoding="utf-8")
    assert "MOCKED" in log and "403" in log
    assert (OUT / "phase5_step3_reconciliation-strong.csv").exists()


def test_every_claim_sourced_or_assumption():
    for p in OUT.glob("phase1_step2_claims-*.json"):
        for c in json.loads(p.read_text(encoding="utf-8"))["claims"]:
            assert c["label"] in ("SOURCED", "ASSUMPTION")
            if c["label"] == "SOURCED":
                assert c["url"] and c["quote"]


def test_strong_preview_banner_after_override():
    for name in ("phase3_step1_product-spec-strong.md", "phase4_step1_pricing-strong.md"):
        p = OUT / name
        if p.exists():
            assert "demand not yet proven" in p.read_text(encoding="utf-8")


def test_only_canonical_outcomes_in_gate_files():
    for p in OUT.glob("phase*_gate_*.md"):
        m = re.search(r"## Outcome: (\w+)", p.read_text(encoding="utf-8"))
        if m:
            assert m.group(1).lower() in ("go", "repeat", "pivot", "stop"), p.name
