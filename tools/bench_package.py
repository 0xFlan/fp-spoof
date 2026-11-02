"""Measure what actually ships.

Run from the repo root: python tools/bench_package.py
"""

import gzip
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SKIP = {".git", ".venv", "artifacts", "__pycache__", ".pytest_cache", "node_modules"}


def files(base):
    for path in base.rglob("*"):
        if any(part in SKIP for part in path.parts):
            continue
        if path.is_file():
            yield path


def measure(base):
    raw = packed = count = 0
    for path in files(base):
        data = path.read_bytes()
        raw += len(data)
        packed += len(gzip.compress(data, 9))
        count += 1
    return raw, packed, count


def human(size):
    return "%.1f KB" % (size / 1024.0)


def main():
    print("%-28s %10s %10s %6s" % ("path", "raw", "gzip", "files"))
    for name in ("extension", "launcher", "fpr", "api", "models", "tests", "tools"):
        raw, packed, count = measure(ROOT / name)
        print("%-28s %10s %10s %6d" % (name, human(raw), human(packed), count))
    raw, packed, count = measure(ROOT)
    print("%-28s %10s %10s %6d" % ("total", human(raw), human(packed), count))
    mirror = ROOT / "extension" / "personas.json"
    if mirror.exists():
        data = mirror.read_bytes()
        print("persona mirror: %s (%.0f%% of the total)"
              % (human(len(data)), 100.0 * len(data) / raw))
        print("personas in mirror: %d" % len(json.loads(data).get("personas") or {}))


if __name__ == "__main__":
    main()
