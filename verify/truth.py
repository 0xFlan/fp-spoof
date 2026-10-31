"""Ground-truth loader.

Reads data/browsers.json. ONLY verifier code may import this module: the
generator (synth/) must never read the truth set, or the score becomes a
function of the tables it sampled from.

Only os.<platform>.mem and os.<platform>.conc are consumed. They are the two
fields a population audit can compare against a curated catalogue; the rest
of the old file was dead weight that made it unclear which numbers actually
constrained the generator.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

from fpr.entropy import empirical

ROOT = Path(__file__).resolve().parents[1]
TRUTH_PATH = ROOT / "data" / "browsers.json"


def path() -> Path:
    """Where to read truth from.

    FP_SPOOF_TRUTH exists because a non-editable install puts the package in
    site-packages while the catalogue stays beside the source tree.
    """
    override = os.environ.get("FP_SPOOF_TRUTH")
    return Path(override) if override else TRUTH_PATH


def load() -> dict:
    with open(path(), encoding="utf-8") as handle:
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
