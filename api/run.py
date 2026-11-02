"""Public API: mint a persona, probe a persona.

``make_profile`` used to hardcode ``fpjs=1.0`` and ``entropy=50.0`` (the latter
because the entropy helper returned a list), so every stored row was identical
and the numbers meant nothing.  It also inserted a new row on every call, so
re-running the CLI multiplied duplicates.
"""

from __future__ import annotations

import random
from typing import Any, Dict, Optional, Tuple

from fix.reconcile import is_valid
from fpr.fingerprint import entropy_bits, entropy_floor, gen
from models.store import bump_hits, upsert
from verify.fingerprintjs_vX import fingerprint
from verify.score import score as acceptance


def make_profile(
    browser: str = "chrome",
    platform: str = "windows",
    seed: int = 111,
    pool: str = "default",
    name: Optional[str] = None,
    store: bool = True,
    version: Optional[str] = None,
) -> Tuple[bool, Dict[str, Any]]:
    """Generate one persona and, when accepted, persist it."""
    rng = random.Random(seed)
    persona = gen(rng, browser, platform, version=version)
    accepted, details = acceptance(persona)
    valid = is_valid(persona) and bool(accepted)
    persona["_accepted"] = valid
    persona["_bits"] = details["bits"]
    persona["_score"] = details["fpjs"]
    if valid and store:
        name = name or "profile-%s-%s" % (browser, platform)
        persona["name"] = name
        upsert(
            name=name,
            pool=pool,
            browser=browser,
            platform=platform,
            entropy=details["bits"],
            fpjs=details["fpjs"],
            persona=persona,
        )
    return valid, persona


def probe_profile(
    browser: str = "chrome",
    platform: str = "windows",
    seed: int = 3003,
) -> Tuple[float, float]:
    """``(coherence score, entropy bits)`` for a freshly generated persona."""
    rng = random.Random(seed)
    persona = gen(rng, browser, platform)
    return fingerprint(persona), entropy_bits(persona)


def generate(
    browser: str = "chrome",
    platform: str = "windows",
    seed: int = 0,
    version: Optional[str] = None,
) -> Dict[str, Any]:
    """Generate a persona without touching the store."""
    return gen(random.Random(seed), browser, platform, version=version)


def validate(persona: Any) -> Dict[str, Any]:
    """Accept/reject a persona and explain why."""
    ok, details = acceptance(persona)
    return {"ok": ok, **details}


def record_hit(name: str) -> None:
    bump_hits(name)


if __name__ == "__main__":  # pragma: no cover - manual smoke test
    import json

    from fpr import catalog
    from models.store import close

    for browser, platform in catalog.combos():
        ok, persona = make_profile(browser, platform, seed=111, store=False)
        fp, bits = probe_profile(browser, platform)
        print("%-6s %-8s valid=%-5s bits=%-5.1f fp=%.2f %s"
              % (browser, platform, ok, bits, fp, persona["ua"][:60]))
    print(json.dumps(validate(generate()), indent=2, default=str))
    close()
