"""Strip indentation and blank lines from the shipped extension sources.

The extension is loaded unpacked, so every byte in ``extension/src`` ships.
Indentation and blank lines aid review but not the browser, and the raw package
has a budget. This removes only leading/trailing whitespace per line and empty
lines: no code, comments, strings or control flow are touched, so the result
stays auditable and ``node --check`` still parses it.

Idempotent: run it after editing any shipped file.
"""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "extension" / "src"
SUFFIXES = {".js", ".css", ".html"}


def compact(text: str) -> str:
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    return "\n".join(lines) + "\n"


def main() -> int:
    saved = 0
    for path in sorted(SRC.iterdir()):
        if path.suffix not in SUFFIXES or not path.is_file():
            continue
        before = path.read_text(encoding="utf-8")
        after = compact(before)
        if after != before:
            path.write_text(after, encoding="utf-8")
            saved += len(before.encode("utf-8")) - len(after.encode("utf-8"))
    print("slimmed extension sources: %d bytes saved" % saved)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
