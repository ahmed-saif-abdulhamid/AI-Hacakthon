"""Settings for the HTTP layer, read once when the process starts."""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TEMPLATES_DIR = ROOT / "templates"
STATIC_DIR = ROOT / "static"
BRIEFS_DIR = ROOT / "briefs"
PROMOTED_RUNS_FILE = ROOT / "runs" / "promoted" / "runs.json"

VERSION = "0.2.0"
API_PREFIX = "/api/v1"  # every JSON route lives under this prefix
DEMO = os.environ.get("PROVEIT_DEMO") == "1"  # read-only public demo of the committed runs

_GIT_TIMEOUT_S = 3


def _git_commit() -> str:
    """The short commit hash of the checkout, or "" when git is unavailable (e.g. in the image)."""
    try:
        return subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"], cwd=ROOT, capture_output=True, text=True, timeout=_GIT_TIMEOUT_S
        ).stdout.strip()
    except (OSError, subprocess.SubprocessError):
        return ""


COMMIT = _git_commit()
