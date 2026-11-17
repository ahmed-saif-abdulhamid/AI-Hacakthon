"""SQLite storage (WAL mode, busy_timeout) shared by the UI worker and the API.

The path comes from PROVEIT_DB. ``:memory:`` keeps one shared connection so tests
never touch the files on disk.
"""

from __future__ import annotations

import os
import sqlite3
import threading
import time
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
MEMORY = ":memory:"
# How long a statement waits for another connection's write lock before failing with "database is locked".
LOCK_TIMEOUT_SECONDS = 5

SCHEMA = """
CREATE TABLE IF NOT EXISTS runs (
    id TEXT PRIMARY KEY, created_at TEXT, label TEXT, mode TEXT, brief_json TEXT,
    stage TEXT, status TEXT, thresholds_sha256 TEXT, outcome TEXT, override_reason TEXT,
    state_json TEXT DEFAULT '{}'
);
CREATE TABLE IF NOT EXISTS actions (
    seq INTEGER PRIMARY KEY AUTOINCREMENT, run_id TEXT, timestamp TEXT, agent TEXT,
    action TEXT, sources TEXT, model TEXT, cost REAL, approved_by TEXT, extra TEXT
);
CREATE TABLE IF NOT EXISTS approvals (
    id TEXT PRIMARY KEY, run_id TEXT, action TEXT, payload_sha256 TEXT, status TEXT,
    decided_by TEXT, decided_at TEXT, created_at TEXT, note TEXT
);
CREATE TABLE IF NOT EXISTS blobs (sha256 TEXT PRIMARY KEY, payload BLOB, content_type TEXT);
CREATE TABLE IF NOT EXISTS published (
    run_id TEXT, kind TEXT, sha256 TEXT, published_at TEXT, PRIMARY KEY (run_id, kind)
);
CREATE TABLE IF NOT EXISTS signups (
    id INTEGER PRIMARY KEY AUTOINCREMENT, run_id TEXT, email TEXT, ts TEXT, test INTEGER
);
CREATE TABLE IF NOT EXISTS orders (
    id TEXT PRIMARY KEY, run_id TEXT, amount REAL, status TEXT, created_at TEXT, test INTEGER
);
CREATE TABLE IF NOT EXISTS payments (
    event_id TEXT PRIMARY KEY, order_id TEXT, amount REAL, fee REAL, net REAL,
    payout_id TEXT, created_at TEXT, test INTEGER
);
CREATE TABLE IF NOT EXISTS payouts (id TEXT PRIMARY KEY, amount REAL, created_at TEXT, test INTEGER);
CREATE TABLE IF NOT EXISTS webhook_events (
    event_id TEXT PRIMARY KEY, type TEXT, received_at TEXT, payload TEXT
);
CREATE TABLE IF NOT EXISTS deliveries (
    order_id TEXT PRIMARY KEY, token TEXT, issued_at TEXT, revoked INTEGER DEFAULT 0
);
CREATE TABLE IF NOT EXISTS telemetry (
    seq INTEGER PRIMARY KEY AUTOINCREMENT, run_id TEXT, ts TEXT, phase INTEGER, kind TEXT,
    text TEXT, data TEXT
);
CREATE TABLE IF NOT EXISTS refunds (
    order_id TEXT PRIMARY KEY, approval_id TEXT, amount REAL, created_at TEXT
);
CREATE TABLE IF NOT EXISTS run_locks (run_id TEXT PRIMARY KEY, locked_at REAL);
"""
# A run lock older than this is treated as left behind by a crashed process and may be taken over.
RUN_LOCK_TTL_SECONDS = 300.0

_lock = threading.RLock()
_memory_conn: sqlite3.Connection | None = None
_initialised: set[str] = set()


def db_path() -> str:
    return os.environ.get("PROVEIT_DB", str(ROOT / "data" / "proveit.db"))


def _new_connection(path: str, **kwargs: object) -> sqlite3.Connection:
    """A connection with rows as mappings and a bounded wait for locks."""
    conn = sqlite3.connect(path, timeout=LOCK_TIMEOUT_SECONDS, **kwargs)
    conn.row_factory = sqlite3.Row
    conn.execute(f"PRAGMA busy_timeout={LOCK_TIMEOUT_SECONDS * 1000}")
    return conn


def _open(path: str) -> sqlite3.Connection:
    global _memory_conn
    if path == MEMORY:
        if _memory_conn is None:
            _memory_conn = _new_connection(MEMORY, check_same_thread=False)
            _memory_conn.executescript(SCHEMA)
        return _memory_conn
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    conn = _new_connection(path)
    if path not in _initialised:
        conn.execute("PRAGMA journal_mode=WAL")
        conn.executescript(SCHEMA)
        _initialised.add(path)
    return conn


@contextmanager
def connect() -> Iterator[sqlite3.Connection]:
    """A connection for one unit of work: committed on success, closed afterwards (file databases)."""
    path = db_path()
    with _lock:
        conn = _open(path)
        try:
            yield conn
            conn.commit()
        finally:
            if path != MEMORY:
                conn.close()


def execute(sql: str, params: tuple = ()) -> None:
    with connect() as c:
        c.execute(sql, params)


def query(sql: str, params: tuple = ()) -> list[dict]:
    with connect() as c:
        return [dict(r) for r in c.execute(sql, params).fetchall()]


def query_one(sql: str, params: tuple = ()) -> dict | None:
    rows = query(sql, params)
    return rows[0] if rows else None


def acquire_run_lock(run_id: str, ttl_s: float = RUN_LOCK_TTL_SECONDS) -> bool:
    """Take the lock on one run for this process; False when another holder has it.

    Atomic across processes: ``BEGIN IMMEDIATE`` takes SQLite's write lock before the stale row is
    removed and the new one inserted, so two processes can never both see the row missing.
    """
    now = time.time()
    with connect() as c:
        if c.in_transaction:
            c.commit()
        c.execute("BEGIN IMMEDIATE")
        try:
            c.execute("DELETE FROM run_locks WHERE run_id=? AND locked_at < ?", (run_id, now - ttl_s))
            taken = c.execute("INSERT OR IGNORE INTO run_locks (run_id, locked_at) VALUES (?, ?)", (run_id, now))
            acquired = taken.rowcount == 1
        except BaseException:
            c.rollback()
            raise
    return acquired


def release_run_lock(run_id: str) -> None:
    execute("DELETE FROM run_locks WHERE run_id=?", (run_id,))


def reset_memory() -> None:
    """Drop the shared in-memory database (tests only)."""
    global _memory_conn
    with _lock:
        if _memory_conn is not None:
            _memory_conn.close()
        _memory_conn = None
        _initialised.clear()
