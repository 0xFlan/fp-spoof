"""Aggregate acceptance score for a persona.

The original imported ``from random.fingerprint import ...`` — a module that
does not exist — so this file raised ``ModuleNotFoundError`` on import and was
never actually called by the API.
"""

from __future__ import annotations

from typing import Any, Dict, List, Tuple

from fix.reconcile import reconcile
from fpr.fingerprint import entropy_bits
from verify.fingerprintjs_vX import fingerprint

MIN_BITS = 12.0
HARD_SCORE = 0.95


def score(
    profile: Any,
    hard: float = HARD_SCORE,
    min_bits: float = MIN_BITS,
) -> Tuple[bool, Dict[str, Any]]:
    """``(accepted, details)`` for a persona.

    Rejects on any hard consistency error, then on a low coherence score, then
    on insufficient entropy.
    """
    problems: List[str] = reconcile(profile)
    bits = entropy_bits(profile) if profile else 0.0
    fp = fingerprint(profile) if profile else 0.0
    details: Dict[str, Any] = {"fpjs": fp, "bits": bits, "errors": problems}

    if problems:
        details["reason"] = ["inconsistent"]
        return False, details
    if fp < hard:
        details["reason"] = ["fpjs-low"]
        return False, details
    if bits < min_bits:
        details["reason"] = ["low-entropy"]
        return False, details

    details["reason"] = []
    return True, details
