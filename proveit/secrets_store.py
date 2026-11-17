"""The signing secret for download links and mock webhooks.

If SECRET_KEY is unset or still the public placeholder, a random secret is generated once and kept in
the data folder (never in git), so a value anyone can read in the repository is never the live secret.
"""

from __future__ import annotations

import os
import secrets
from functools import lru_cache

from .startup import data_dir

PLACEHOLDERS = {"", "dev-only-change-me", "change-me-to-a-random-string", "test-secret-placeholder"}


@lru_cache(maxsize=1)
def secret_key() -> str:
    env = os.environ.get("SECRET_KEY", "").strip()
    if env and env not in PLACEHOLDERS:
        return env
    if os.environ.get("PROVEIT_ENV") == "test" and env:
        return env
    path = data_dir() / "secret_key"
    try:
        if path.exists():
            value = path.read_text(encoding="utf-8").strip()
            if value:
                return value
        path.parent.mkdir(parents=True, exist_ok=True)
        value = secrets.token_hex(32)
        path.write_text(value, encoding="utf-8")
        return value
    except OSError:
        # Read-only file system (the hosted demo): a per-process secret still beats a public one.
        return secrets.token_hex(32)
