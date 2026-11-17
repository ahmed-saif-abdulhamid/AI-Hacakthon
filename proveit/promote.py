"""promote: the only writer of outputs/. Copies two runs' files with -weak / -strong
suffixes, plus payment_test_log.md, and writes runs/promoted/decision_log.json and runs.json.
Each run file also gets one canonical unsuffixed copy (e.g. phase1_step1_opportunities.md):
from the strong run, except the files listed in CANONICAL_FROM.
``make promote`` (or --root) copies runs/promoted/decision_log.json to the repo root."""

from __future__ import annotations

import json
import re
import shutil
from pathlib import Path

from . import log, seed
from .startup import ROOT, outputs_dir, runs_dir

PAYMENT_LOG = "payment_test_log.md"
RUN_FILE_RE = re.compile(r"^phase\d+_(step\d+|gate)_[a-z0-9-]+\.(md|json|csv|txt|html)$")
# A promoted output: a run file with its -weak / -strong suffix, or the payment test log.
NAME_RE = re.compile(r"^(phase\d+_(step\d+|gate)_[a-z0-9-]+|payment_test_log)\.(md|json|csv|txt|html)$")
# Which run supplies the canonical unsuffixed copy of a file; any file not listed comes from the strong run.
# The phase 1 gate comes from the weak run so the plain gate decision shows the system recommending STOP.
CANONICAL_DEFAULT = "strong"
CANONICAL_FROM = {"phase1_gate_decision.md": "weak"}


def promote(weak_id: str, strong_id: str, to_root: bool = False) -> dict:
    """Replace outputs/ with the two runs' files and record what was promoted. Returns runs.json's content."""
    copied = _copy_outputs({"weak": weak_id, "strong": strong_id})
    entries = log.export(weak_id) + log.export(strong_id)
    promoted = runs_dir() / "promoted"
    promoted.mkdir(parents=True, exist_ok=True)
    _write(promoted / "decision_log.json", json.dumps(entries, indent=1, ensure_ascii=False) + "\n")
    meta = {
        "weak": weak_id,
        "strong": strong_id,
        "entries": len(entries),
        "entries_weak": sum(1 for e in entries if e["run_id"] == weak_id),
        "entries_strong": sum(1 for e in entries if e["run_id"] == strong_id),
        "outputs": copied,
        "seed": seed.export([weak_id, strong_id]),
    }
    _write(promoted / "runs.json", json.dumps(meta, indent=2) + "\n")
    if to_root:
        shutil.copyfile(promoted / "decision_log.json", ROOT / "decision_log.json")
    return meta


def _copy_outputs(runs: dict[str, str]) -> list[str]:
    """Clear the promoted files from outputs/ and copy each run's files in, suffixed with its label."""
    out = outputs_dir()
    out.mkdir(parents=True, exist_ok=True)
    for old in out.iterdir():
        if old.is_file() and NAME_RE.match(old.name):
            old.unlink()
    copied = []
    for label, run_id in runs.items():
        src = runs_dir() / run_id
        if not src.exists():
            raise FileNotFoundError(src)
        for f in sorted(src.iterdir()):
            for target in _targets(out, f.name, label):
                _write(target, f.read_text(encoding="utf-8"))
                copied.append(target.name)
    return copied


def _targets(out: Path, name: str, label: str) -> list[Path]:
    """Where one run file goes: its suffixed copy, plus the canonical plain copy if this run supplies it."""
    target = _target(out, name, label)
    if target is None:
        return []
    if RUN_FILE_RE.match(name) and CANONICAL_FROM.get(name, CANONICAL_DEFAULT) == label:
        return [target, out / name]
    return [target]


def _target(out: Path, name: str, label: str) -> Path | None:
    if name == PAYMENT_LOG:
        return out / name
    if RUN_FILE_RE.match(name):
        stem, ext = name.rsplit(".", 1)
        return out / f"{stem}-{label}.{ext}"
    return None


def _write(path: Path, text: str) -> None:
    path.write_text(text, encoding="utf-8", newline="\n")
