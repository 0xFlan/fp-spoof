import sqlite3, os, json

DBPATH = "/tmp/dd2dl/fp-spoof/pools/profiles.db"

def _connect():
    os.makedirs(os.path.dirname(DBPATH), exist_ok=True)
    return sqlite3.connect(DBPATH)

def init_db():
    con = _connect()
    con.execute("""CREATE TABLE IF NOT EXISTS profiles (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT, pool TEXT, browser TEXT, platform TEXT,
        entropy_bits REAL, fpjs REAL, hits INTEGER, created TEXT)""")
    con.commit()
    con.close()
    return

def insert(name, pool, browser, platform, entropy, fpjs, hits=0):
    init_db()
    con = _connect()
    con.execute(
        "INSERT INTO profiles(name,pool,browser,platform,entropy_bits,fpjs,hits,created) VALUES(?,?,?,?,?,?,0,?)",
        (name, pool, browser, platform, round(float(entropy), 3), round(float(fpjs), 3), "2026-10-01T00:00:00Z"))
    con.commit()
    con.close()

def list_profiles():
    con = _connect()
    rows = con.execute("SELECT name,pool,browser,platform,entropy_bits,fpjs,hits FROM profiles ORDER BY id").fetchall()
    con.close()
    return rows
