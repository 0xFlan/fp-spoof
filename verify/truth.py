"""Ground-truth loader.

Reads data/browsers.json. ONLY verifier code may import this module: the
generator (synth/) must never read the truth set, or the score becomes a
function of the tables it sampled from.
"""
from __future__ import annotations

import json
from pathlib import Path

from fpr.entropy import empirical

ROOT = Path(__file__).resolve().parents[1]
TRUTH_PATH = ROOT / "data" / "browsers.json"


def load() -> dict:
    with open(TRUTH_PATH, encoding="utf-8") as handle:
        return json.load(handle)


def platforms() -> list:
    return sorted(load().get("os", {}))


def distributions(platform: str) -> dict:
    """Truth for one platform as frequency tables.

    The catalogue lists plausible values rather than counts, so the listed
    order is treated as uniform and duplicates count as weight (mac lists 8
    twice, which is the intended weighting).
    """
    os_table = load().get("os", {}).get(platform, {})
    out = {}
    if "mem" in os_table:
        out["deviceMemory"] = empirical(os_table["mem"])
    if "conc" in os_table:
        out["hardwareConcurrency"] = empirical(os_table["conc"])
    return out
