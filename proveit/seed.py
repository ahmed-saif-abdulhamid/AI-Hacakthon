"""The committed demo runs, loadable into a fresh install.

``promote`` exports the two promoted runs (their database rows and run folders) to
runs/promoted/. On start-up the console loads them when they are missing, so a fresh
``docker compose up``, even without an NVIDIA key, opens real recorded runs instead of
an empty screen. Sign-up emails, delivery tokens and console chat are never exported.
"""

from __future__ import annotations

import base64
import json
import shutil

from . import db
from .startup import ROOT, runs_dir

PROMOTED = ROOT / "runs" / "promoted"
SEED = PROMOTED / "seed.json"
# table -> (column holding the run id, or a sub-query for tables keyed through orders)
TABLES = {
    "runs": "id IN ({q})",
    "actions": "run_id IN ({q}) AND agent NOT IN ('assistant', 'ask')",
    "approvals": "run_id IN ({q})",
    "published": "run_id IN ({q})",
    "orders": "run_id IN ({q})",
    "telemetry": "run_id IN ({q})",
    "payments": "order_id IN (SELECT id FROM orders WHERE run_id IN ({q}))",
    "refunds": "order_id IN (SELECT id FROM orders WHERE run_id IN ({q}))",
    "blobs": "sha256 IN (SELECT payload_sha256 FROM approvals WHERE run_id IN ({q}))",
}


def _trim_state(state_json: str) -> str:
    """Keep the sentences of hits that became claims; other posts keep only their link and title."""
    state = json.loads(state_json or "{}")
    used = {c.get("hit_id") for c in state.get("claims", [])}
    for research in (state.get("research") or {}).values():
        if not isinstance(research, dict):
            continue
        used |= {c.get("hit_id") for c in research.get("claims", [])}
        for hid, hit in (research.get("hits") or {}).items():
            if hid not in used and isinstance(hit, dict):
                hit["sentences"] = []
    return json.dumps(state, ensure_ascii=False)


def export(run_ids: list[str]) -> dict:
    """Write the runs' rows to seed.json and their folders to runs/promoted/. Returns rows per table."""
    q = ",".join("?" * len(run_ids))
    data: dict = {"runs_ids": run_ids, "tables": {}}
    for table, where in TABLES.items():
        rows = db.query(f"SELECT * FROM {table} WHERE {where.format(q=q)}", tuple(run_ids))
        for r in rows:
            r.pop("seq", None)
            if table == "runs":
                r["state_json"] = _trim_state(r["state_json"])
            if table == "blobs" and isinstance(r.get("payload"), bytes | bytearray):
                r["payload"] = {"b64": base64.b64encode(r["payload"]).decode()}
        data["tables"][table] = rows
    PROMOTED.mkdir(parents=True, exist_ok=True)
    SEED.write_text(json.dumps(data, indent=0, ensure_ascii=False) + "\n", encoding="utf-8", newline="\n")
    for rid in run_ids:
        dst = PROMOTED / rid
        if dst.exists():
            shutil.rmtree(dst)
        shutil.copytree(runs_dir() / rid, dst)
    for old in PROMOTED.iterdir():  # drop folders of runs no longer promoted
        if old.is_dir() and old.name.startswith("r") and old.name not in run_ids:
            shutil.rmtree(old)
    return {t: len(v) for t, v in data["tables"].items()}


def load() -> list[str]:
    """Insert the committed runs that this database does not have yet. Returns the ids loaded."""
    if not SEED.exists():
        return []
    data = json.loads(SEED.read_text(encoding="utf-8"))
    loaded = []
    for rid in data["runs_ids"]:
        src, dst = PROMOTED / rid, runs_dir() / rid
        if src.exists() and not dst.exists():
            shutil.copytree(src, dst)
        if db.query_one("SELECT id FROM runs WHERE id=?", (rid,)):
            continue
        loaded.append(rid)
    if not loaded:
        return []
    with db.connect() as c:
        for table, rows in data["tables"].items():
            for r in rows:
                if not _belongs_to(table, r, loaded):
                    continue
                if table == "blobs" and isinstance(r.get("payload"), dict):
                    r = {**r, "payload": base64.b64decode(r["payload"]["b64"])}
                cols = ",".join(r)
                c.execute(
                    f"INSERT OR IGNORE INTO {table} ({cols}) VALUES ({','.join('?' * len(r))})", tuple(r.values())
                )
    return loaded


def _belongs_to(table: str, row: dict, run_ids: list[str]) -> bool:
    """False for a row of a run that is not being loaded (rows keyed through orders always load)."""
    if table == "runs":
        return row["id"] in run_ids
    return "run_id" not in row or row["run_id"] in run_ids
