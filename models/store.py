"""SQLite persona store.

Fixes over the original:

* the database lived at ``/tmp/dd2dl/fp-spoof/pools/profiles.db`` — a leftover
  path from an unrelated project, wiped on reboot, and unwritable for other
  users. It now lives under ``$FPSPOOF_HOME`` (default ``~/.fp-spoof``);
* ``init_db()`` was called on *every* insert, opening and closing three
  connections per profile;
* there was no unique constraint, so re-running the CLI duplicated every row;
* ``created`` was hardcoded to ``2026-10-01T00:00:00Z``;
* rows came back as anonymous tuples and the persona itself was never stored.
"""

from __future__ import annotations

import json
import os
import sqlite3
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

DEFAULT_HOME = Path.home() / ".fp-spoof"

_SCHEMA = """
CREATE TABLE IF NOT EXISTS profiles (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    name         TEXT NOT NULL UNIQUE,
    pool         TEXT NOT NULL DEFAULT 'default',
    browser      TEXT NOT NULL,
    platform     TEXT NOT NULL,
    persona      TEXT NOT NULL,
    entropy_bits REAL NOT NULL,
    score        REAL NOT NULL,
    hits         INTEGER NOT NULL DEFAULT 0,
    created      TEXT NOT NULL,
    updated      TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_profiles_pool ON profiles(pool, platform, browser);
"""

_lock = threading.RLock()
_connections: Dict[str, sqlite3.Connection] = {}
_initialised: set = set()


def home() -> Path:
    return Path(os.environ.get("FPSPOOF_HOME") or DEFAULT_HOME).expanduser()


def db_path() -> Path:
    override = os.environ.get("FPSPOOF_DB")
    if override:
        return Path(override).expanduser()
    return home() / "pools" / "profiles.db"


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _connect() -> sqlite3.Connection:
    path = db_path()
    key = str(path)
    with _lock:
        conn = _connections.get(key)
        if conn is not None:
            return conn
        path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(key, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA synchronous=NORMAL")
        _connections[key] = conn
        return conn


def init_db() -> None:
    """Create the schema once per database file."""
    key = str(db_path())
    with _lock:
        if key in _initialised:
            return
        conn = _connect()
        conn.executescript(_SCHEMA)
        conn.commit()
        _initialised.add(key)


def close() -> None:
    """Close cached connections (tests and CLI shutdown)."""
    with _lock:
        for conn in _connections.values():
            try:
                conn.close()
            except sqlite3.Error:
                pass
        _connections.clear()
        _initialised.clear()


def _encode(persona: Any) -> str:
    if persona is None:
        return "{}"
    if hasattr(persona, "to_dict"):
        persona = persona.to_dict()
    if isinstance(persona, dict):
        return json.dumps(persona, sort_keys=True, default=str)
    return json.dumps({"value": persona}, default=str)


def upsert(
    name: str,
    pool: str = "default",
    browser: str = "chrome",
    platform: str = "windows",
    entropy: float = 0.0,
    fpjs: float = 0.0,
    hits: int = 0,
    persona: Any = None,
) -> str:
    """Insert or replace a profile by name. Returns the profile name."""
    init_db()
    conn = _connect()
    now = _now()
    with _lock:
        conn.execute(
            """
            INSERT INTO profiles (name, pool, browser, platform, persona,
                                  entropy_bits, score, hits, created, updated)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(name) DO UPDATE SET
                pool=excluded.pool,
                browser=excluded.browser,
                platform=excluded.platform,
                persona=excluded.persona,
                entropy_bits=excluded.entropy_bits,
                score=excluded.score,
                updated=excluded.updated
            """,
            (name, pool, browser, platform, _encode(persona),
             round(float(entropy), 4), round(float(fpjs), 4), int(hits), now, now),
        )
        conn.commit()
    return name


def insert(*args: Any, **kwargs: Any) -> str:
    """Backwards-compatible alias for :func:`upsert`."""
    return upsert(*args, **kwargs)


def get(name: str) -> Optional[Dict[str, Any]]:
    init_db()
    conn = _connect()
    with _lock:
        row = conn.execute("SELECT * FROM profiles WHERE name = ?", (name,)).fetchone()
    return _row(row) if row else None


def list_profiles(pool: Optional[str] = None) -> List[Dict[str, Any]]:
    """All profiles, newest last. Safe on an empty database."""
    init_db()
    conn = _connect()
    sql = "SELECT * FROM profiles"
    params: tuple = ()
    if pool:
        sql += " WHERE pool = ?"
        params = (pool,)
    sql += " ORDER BY id"
    with _lock:
        rows = conn.execute(sql, params).fetchall()
    return [_row(row) for row in rows]


def delete(name: str) -> bool:
    init_db()
    conn = _connect()
    with _lock:
        cur = conn.execute("DELETE FROM profiles WHERE name = ?", (name,))
        conn.commit()
    return cur.rowcount > 0


def bump_hits(name: str) -> None:
    init_db()
    conn = _connect()
    with _lock:
        conn.execute(
            "UPDATE profiles SET hits = hits + 1, updated = ? WHERE name = ?", (_now(), name)
        )
        conn.commit()


def count() -> int:
    init_db()
    conn = _connect()
    with _lock:
        row = conn.execute("SELECT COUNT(*) AS n FROM profiles").fetchone()
    return int(row["n"]) if row else 0


def unique_name(prefix: str = "profile") -> str:
    return "%s-%s" % (prefix, uuid.uuid4().hex[:8])


def _row(row: sqlite3.Row) -> Dict[str, Any]:
    out = dict(row)
    try:
        out["persona"] = json.loads(out.get("persona") or "{}")
    except ValueError:
        out["persona"] = {}
    return out
