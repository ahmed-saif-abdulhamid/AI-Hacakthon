"""promote: the only writer of outputs/. Copies two runs' files with -weak / -strong
suffixes, plus payment_test_log.md, and writes runs/promoted/decision_log.json and runs.json.
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
            target = _target(out, f.name, label)
            if target is not None:
                _write(target, f.read_text(encoding="utf-8"))
                copied.append(target.name)
    return copied


def _target(out: Path, name: str, label: str) -> Path | None:
    if name == PAYMENT_LOG:
        return out / name
    if RUN_FILE_RE.match(name):
        stem, ext = name.rsplit(".", 1)
        return out / f"{stem}-{label}.{ext}"
    return None


def _write(path: Path, text: str) -> None:
    path.write_text(text, encoding="utf-8", newline="\n")
