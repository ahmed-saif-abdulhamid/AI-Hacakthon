"""Build the read-only public demo for Vercel into deploy/vercel_site/ (not committed).

The hosted demo shows the two committed runs (weak -> STOP, strong -> preview after override)
with the same console. It never runs the pipeline (no key is shipped for that), so starting runs,
gate decisions, approvals, purchases and refunds return 403. The assistant answers from the
recorded run without a model, and speech uses the browser's own voice.

Usage:  python deploy/build_vercel.py   then   cd deploy/vercel_site && npx vercel deploy --prod
"""

from __future__ import annotations

import json
import shutil
import sqlite3
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "deploy" / "vercel_site"
CODE_DIRS = ["proveit", "agents", "sources", "templates", "static", "config", "prompts", "briefs"]
CODE_FILES = [
    "delivery.py",
    "payments.py",
    "refunds.py",
    "webhooks.py",
    "reconcile.py",
    "approval.py",
    "gates.py",
    "orchestrator.py",
    "LICENSE",
]
REQUIREMENTS = """fastapi==0.116.1
Jinja2==3.1.6
pydantic==2.11.7
PyYAML==6.0.2
httpx==0.28.1
rapidfuzz==3.13.0
itsdangerous==2.2.0
python-multipart==0.0.20
snowballstemmer==3.0.1
pysbd==0.3.4
beautifulsoup4==4.13.4
"""
ENTRY = '''"""Vercel entrypoint: the ProveIt console as a read-only demo of the committed runs."""
import os
import secrets
import shutil
from pathlib import Path

HERE = Path(__file__).resolve().parent
TMP = Path("/tmp/proveit")
TMP.mkdir(parents=True, exist_ok=True)
DB = TMP / "proveit.db"
if not DB.exists():
    shutil.copy(HERE / "demo" / "proveit.db", DB)
os.environ["PROVEIT_DEMO"] = "1"
os.environ["PROVEIT_DB"] = str(DB)
os.environ["PROVEIT_RUNS"] = str(HERE / "runs")
os.environ["PROVEIT_OUTPUTS"] = str(TMP / "outputs")
os.environ["PROVEIT_DATA"] = str(TMP / "data")
os.environ.setdefault("SECRET_KEY", secrets.token_hex(16))

from app.api import app  # noqa: E402,F401
'''


def ignore(_dir, names):
    return [n for n in names if n in ("__pycache__", ".pytest_cache") or n.endswith(".pyc")]


def build() -> Path:
    promoted = json.loads((ROOT / "runs" / "promoted" / "runs.json").read_text(encoding="utf-8"))
    keep = [promoted["weak"], promoted["strong"]]
    OUT.mkdir(parents=True, exist_ok=True)
    for child in OUT.iterdir():  # empty it but keep the folder (and its .vercel link)
        if child.name == ".vercel":
            continue
        shutil.rmtree(child) if child.is_dir() else child.unlink()
    for d in CODE_DIRS:
        shutil.copytree(ROOT / d, OUT / d, ignore=ignore)
    for f in CODE_FILES:
        shutil.copy(ROOT / f, OUT / f)
    shutil.copytree(ROOT / "app", OUT / "app", ignore=ignore)
    for rid in keep:
        shutil.copytree(ROOT / "runs" / rid, OUT / "runs" / rid, ignore=ignore)

    # A database holding only the two committed runs (no sign-up emails, no tokens, no other runs).
    (OUT / "demo").mkdir()
    dst = OUT / "demo" / "proveit.db"
    src = sqlite3.connect(ROOT / "data" / "proveit.db")
    out = sqlite3.connect(dst)
    src.backup(out)
    src.close()
    q = ",".join("?" * len(keep))
    for table in ("runs",):
        out.execute(f"DELETE FROM {table} WHERE id NOT IN ({q})", keep)
    for table in ("actions", "approvals", "published", "orders", "telemetry"):
        out.execute(f"DELETE FROM {table} WHERE run_id IS NULL OR run_id NOT IN ({q})", keep)
    out.execute("DELETE FROM actions WHERE agent IN ('assistant', 'ask')")  # console chat, not the run
    out.execute("DELETE FROM blobs WHERE sha256 NOT IN (SELECT payload_sha256 FROM approvals)")
    out.execute("DELETE FROM payments WHERE order_id NOT IN (SELECT id FROM orders)")
    out.execute("DELETE FROM refunds WHERE order_id NOT IN (SELECT id FROM orders)")
    for table in ("signups", "deliveries", "webhook_events", "payouts"):
        out.execute(f"DELETE FROM {table}")
    out.commit()
    out.execute("PRAGMA journal_mode=DELETE")
    out.execute("VACUUM")
    out.close()

    (OUT / "index.py").write_text(ENTRY, encoding="utf-8")
    (OUT / "requirements.txt").write_text(REQUIREMENTS, encoding="utf-8")
    (OUT / ".python-version").write_text("3.12\n", encoding="utf-8")
    (OUT / "vercel.json").write_text(
        json.dumps(
            {"$schema": "https://openapi.vercel.sh/vercel.json", "functions": {"index.py": {"maxDuration": 30}}},
            indent=2,
        ),
        encoding="utf-8",
    )
    (OUT / ".vercelignore").write_text("__pycache__\n*.pyc\n.vercel\n", encoding="utf-8")
    return OUT


if __name__ == "__main__":
    path = build()
    size = sum(p.stat().st_size for p in path.rglob("*") if p.is_file())
    print(f"built {path} ({size / 1e6:.1f} MB)")
