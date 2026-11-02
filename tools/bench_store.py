"""Store insert benchmark, reproducible on this machine.

Compares the original pattern (a fresh connection and a schema re-create per
row) with the current WAL + upsert path, on a throwaway database. Prints the
measured milliseconds and the speedup; nothing is written to ~/.fp-spoof.

    python tools/bench_store.py
"""

import os
import sqlite3
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

ROWS = 300

SCHEMA = """CREATE TABLE IF NOT EXISTS profiles (
 id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT NOT NULL UNIQUE,
 pool TEXT NOT NULL DEFAULT 'default', browser TEXT NOT NULL, platform TEXT NOT NULL,
 persona TEXT NOT NULL, entropy_bits REAL NOT NULL, score REAL NOT NULL,
 hits INTEGER NOT NULL DEFAULT 0, created TEXT NOT NULL, updated TEXT NOT NULL);"""


def old_way(path: str) -> float:
    start = time.perf_counter()
    for i in range(ROWS):
        conn = sqlite3.connect(path)      # connection per row, as the stub did
        conn.executescript(SCHEMA)        # schema re-created per row
        conn.execute(
            "INSERT INTO profiles (name,pool,browser,platform,persona,entropy_bits,"
            "score,hits,created,updated) VALUES (?,?,?,?,?,?,?,?,?,?)",
            ("old-%d" % i, "default", "chrome", "windows", "{}", 1.0, 1.0, 0, "x", "x"),
        )
        conn.commit()
        conn.close()
    return time.perf_counter() - start


def new_way() -> float:
    from models import store

    start = time.perf_counter()
    for i in range(ROWS):
        store.upsert("new-%d" % i, browser="chrome", platform="windows",
                     entropy=20.0, fpjs=1.0, persona={"screenX": 1600, "n": i})
    return time.perf_counter() - start


def main() -> int:
    tmp = tempfile.mkdtemp(prefix="fpspoof-bench-")
    os.environ["FPSPOOF_HOME"] = tmp
    os.environ["FPSPOOF_DB"] = os.path.join(tmp, "new.db")

    old = old_way(os.path.join(tmp, "old.db"))
    new = new_way()
    from models import store

    new_way()          # same names again: proves the upsert path, not duplicates
    rows = store.count()
    journal = store._connect().execute("PRAGMA journal_mode").fetchone()[0]
    store.close()

    print("rows                     %d" % ROWS)
    print("old (conn+schema/row)    %.1f ms  -> %.0f rows/s" % (old * 1e3, ROWS / old))
    print("new (WAL + upsert)       %.1f ms  -> %.0f rows/s" % (new * 1e3, ROWS / new))
    print("speedup                  %.1fx" % (old / new))
    print("rows after a second run  %d (names deduped, not duplicated)" % rows)
    print("journal_mode             %s" % journal)
    return 0


if __name__ == "__main__":
    sys.exit(main())
