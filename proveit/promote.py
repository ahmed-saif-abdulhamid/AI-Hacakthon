"""promote: the only writer of outputs/. Copies two runs' files with -weak / -strong
suffixes, plus payment_test_log.md, and writes runs/promoted/decision_log.json and runs.json.
``make promote`` (or --root) copies runs/promoted/decision_log.json to the repo root."""
from __future__ import annotations

import json
import re
import shutil

from . import log, seed
from .startup import ROOT, outputs_dir, runs_dir

NAME_RE = re.compile(r"^(phase\d+_(step\d+|gate)_[a-z0-9-]+|payment_test_log)\.(md|json|csv|txt|html)$")


def promote(weak_id: str, strong_id: str, to_root: bool = False) -> dict:
    out = outputs_dir()
    out.mkdir(parents=True, exist_ok=True)
    for old in out.iterdir():
        if old.is_file() and NAME_RE.match(old.name):
            old.unlink()
    copied = []
    for label, run_id in (("weak", weak_id), ("strong", strong_id)):
        src = runs_dir() / run_id
        if not src.exists():
            raise FileNotFoundError(src)
        for f in sorted(src.iterdir()):
            if f.name == "payment_test_log.md":
                target = out / f.name
            elif re.match(r"^phase\d+_(step\d+|gate)_[a-z0-9-]+\.(md|json|csv|txt|html)$", f.name):
                stem, ext = f.name.rsplit(".", 1)
                target = out / f"{stem}-{label}.{ext}"
            else:
                continue
            text = f.read_text(encoding="utf-8")
            target.write_text(text, encoding="utf-8", newline="\n")
            copied.append(target.name)
    entries = log.export(weak_id) + log.export(strong_id)
    promoted = runs_dir() / "promoted"
    promoted.mkdir(parents=True, exist_ok=True)
    data = json.dumps(entries, indent=1, ensure_ascii=False) + "\n"
    (promoted / "decision_log.json").write_text(data, encoding="utf-8", newline="\n")
    meta = {"weak": weak_id, "strong": strong_id, "entries": len(entries),
            "entries_weak": sum(1 for e in entries if e["run_id"] == weak_id),
            "entries_strong": sum(1 for e in entries if e["run_id"] == strong_id), "outputs": copied}
    (promoted / "runs.json").write_text(json.dumps(meta, indent=2) + "\n", encoding="utf-8", newline="\n")
    meta["seed"] = seed.export([weak_id, strong_id])
    (promoted / "runs.json").write_text(json.dumps(meta, indent=2) + "\n", encoding="utf-8", newline="\n")
    if to_root:
        shutil.copyfile(promoted / "decision_log.json", ROOT / "decision_log.json")
    return meta
