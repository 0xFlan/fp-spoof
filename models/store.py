"""SQLite profile store.

One row per (name, pool). Re-saving updates the row and PRESERVES hits; hits
only ever increase through record_hit(). The previous schema had no
uniqueness, so every run appended another identical profile-chrome-windows
row, and no list_profiles() path initialised the table.
"""
from __future__ import annotations

import json
import os
import sqlite3
from contextlib import closing
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

SCHEMA = """
CREATE TABLE IF NOT EXISTS profiles (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    pool TEXT NOT NULL,
    seed INTEGER NOT NULL,
    browser TEXT NOT NULL,
    platform TEXT NOT NULL,
    entropy_bits REAL,
    consistency REAL,
    hits INTEGER NOT NULL DEFAULT 0,
    created TEXT NOT NULL DEFAULT (datetime('now')),
    payload TEXT NOT NULL,
    UNIQUE(name, pool)
);
"""

UPSERT = """
INSERT INTO profiles (name, pool, seed, browser, platform, entropy_bits, consistency, payload)
VALUES (?, ?, ?, ?, ?, ?, ?, ?)
ON CONFLICT(name, pool) DO UPDATE SET
    seed = excluded.seed,
    browser = excluded.browser,
    platform = excluded.platform,
    entropy_bits = excluded.entropy_bits,
    consistency = excluded.consistency,
    payload = excluded.payload
"""

COLUMNS = "name, pool, seed, browser, platform, entropy_bits, consistency, hits"


def dbpath() -> str:
    return os.environ.get("FP_SPOOF_DB", str(ROOT / "var" / "profiles.db"))


def connect() -> sqlite3.Connection:
    path = dbpath()
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    connection = sqlite3.connect(path, timeout=15)
    connection.execute("PRAGMA journal_mode=WAL")
    return connection


def init_db() -> None:
    with closing(connect()) as connection:
        connection.executescript(SCHEMA)
        connection.commit()


def save(profile, entropy_bits=None, consistency=None) -> None:
    init_db()
    payload = json.dumps(profile.to_dict(), sort_keys=True, default=str)
    with closing(connect()) as connection:
        connection.execute(
            UPSERT,
            (
                profile.name,
                profile.pool,
                profile.seed,
                profile.browser,
                profile.platform,
                entropy_bits,
                consistency,
                payload,
            ),
        )
        connection.commit()


def record_hit(name, pool="default") -> int:
    init_db()
    with closing(connect()) as connection:
        cursor = connection.execute(
            "UPDATE profiles SET hits = hits + 1 WHERE name = ? AND pool = ?",
            (name, pool),
        )
        connection.commit()
        return cursor.rowcount


def get(name, pool="default"):
    init_db()
    with closing(connect()) as connection:
        return connection.execute(
            f"SELECT {COLUMNS}, created FROM profiles WHERE name = ? AND pool = ?",
            (name, pool),
        ).fetchone()


def payload(name, pool="default"):
    init_db()
    with closing(connect()) as connection:
        row = connection.execute(
            "SELECT payload FROM profiles WHERE name = ? AND pool = ?", (name, pool)
        ).fetchone()
    return json.loads(row[0]) if row else None


def list_profiles(pool=None):
    init_db()
    with closing(connect()) as connection:
        if pool is None:
            rows = connection.execute(
                f"SELECT {COLUMNS} FROM profiles ORDER BY id"
            ).fetchall()
        else:
            rows = connection.execute(
                f"SELECT {COLUMNS} FROM profiles WHERE pool = ? ORDER BY id", (pool,)
            ).fetchall()
    return rows
