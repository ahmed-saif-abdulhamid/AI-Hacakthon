"""outputs/: names by phase and step, a STOP gate for the weak run, the payment log,
every claim SOURCED or ASSUMPTION, and a canonical unsuffixed copy of each run file."""

from __future__ import annotations

import json
import re
from pathlib import Path

from proveit.promote import CANONICAL_ALIASES, CANONICAL_DEFAULT, CANONICAL_FROM, RUN_FILE_RE, _copy_outputs

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "outputs"
SUFFIXED = re.compile(r"-(weak|strong)$")
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


def test_canonical_plain_names_present():
    for name in ("phase1_step1_opportunities.md", "phase1_gate_decision.md"):
        p = OUT / name
        assert p.exists() and p.stat().st_size > 0, name


def test_plain_phase1_gate_is_the_weak_runs_stop():
    assert "## Outcome: STOP" in (OUT / "phase1_gate_decision.md").read_text(encoding="utf-8")


def test_each_plain_file_matches_its_suffixed_source():
    aliases = set(CANONICAL_ALIASES.values())
    plain = [p for p in files() if RUN_FILE_RE.match(p.name) and not SUFFIXED.search(p.stem) and p.name not in aliases]
    assert len(plain) > 2
    for p in plain:
        label = CANONICAL_FROM.get(p.name, CANONICAL_DEFAULT)
        stem, ext = p.name.rsplit(".", 1)
        assert p.read_bytes() == (OUT / f"{stem}-{label}.{ext}").read_bytes(), p.name


def test_copy_writes_canonical_copies(tmp_path, monkeypatch):
    runs, out = tmp_path / "runs", tmp_path / "outputs"
    for run_id, outcome in (("w", "STOP"), ("s", "GO")):
        (runs / run_id).mkdir(parents=True)
        (runs / run_id / "phase1_gate_decision.md").write_text(f"## Outcome: {outcome}\n", encoding="utf-8")
        (runs / run_id / "phase1_step1_opportunities.md").write_text(run_id, encoding="utf-8")
    monkeypatch.setenv("PROVEIT_RUNS", str(runs))
    monkeypatch.setenv("PROVEIT_OUTPUTS", str(out))
    _copy_outputs({"weak": "w", "strong": "s"})
    assert (out / "phase1_gate_decision.md").read_text(encoding="utf-8") == "## Outcome: STOP\n"
    assert (out / "phase1_step1_opportunities.md").read_text(encoding="utf-8") == "s"
    assert (out / "phase1_step1_opportunities-weak.md").read_text(encoding="utf-8") == "w"
    assert (out / "phase1_gate_decision-strong.md").exists()


def test_core_step_5_2_has_its_phase_step_name():
    alias = ROOT / "outputs" / "phase5_step2_payment-test-log.md"
    assert alias.read_bytes() == (ROOT / "outputs" / "payment_test_log.md").read_bytes()
