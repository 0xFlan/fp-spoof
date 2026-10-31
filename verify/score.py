"""Acceptance gate for a single profile.

Returns (ok, result) where result always carries the same keys, so callers
never have to branch on shape.
"""
from __future__ import annotations

from constants import MIN_CONSISTENCY
from fix.reconcile import reconcile
from verify.fingerprintjs_vX import consistency, fingerprint


def score(profile, min_consistency=MIN_CONSISTENCY):
    errors = reconcile(profile)
    result = {
        "fingerprint": fingerprint(profile),
        "consistency": consistency(profile),
        "errors": errors,
        "reason": None,
    }

    if errors:
        result["reason"] = "inconsistent"
        return False, result
    if result["consistency"] < min_consistency:
        result["reason"] = "low-consistency"
        return False, result

    return True, result
