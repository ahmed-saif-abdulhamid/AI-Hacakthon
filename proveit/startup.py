"""Start-up checks: writable data/outputs/runs directories, with a clear fix if not."""
from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def runs_dir() -> Path:
    return Path(os.environ.get("PROVEIT_RUNS", ROOT / "runs"))


def outputs_dir() -> Path:
    return Path(os.environ.get("PROVEIT_OUTPUTS", ROOT / "outputs"))


def data_dir() -> Path:
    return Path(os.environ.get("PROVEIT_DATA", ROOT / "data"))


def check_writable() -> list[str]:
    problems = []
    for d in (data_dir(), outputs_dir(), runs_dir()):
        try:
            d.mkdir(parents=True, exist_ok=True)
            probe = d / ".write_probe"
            probe.write_text("ok")
            probe.unlink()
        except OSError as e:
            problems.append(f"{d} is not writable ({e}). Fix on a Linux host: chmod a+rwX outputs runs")
    return problems


def main() -> int:
    problems = check_writable()
    for p in problems:
        print("[startup] " + p, file=sys.stderr)
    return 1 if problems else 0


if __name__ == "__main__":
    raise SystemExit(main())
