"""Deterministic hardening material for a persona.

The old ``harden`` crashed on its first call: it indexed an int, i.e.
``p["screenX"]["screenY"]``.  It also returned ``"WebGL/1"`` and ``"WebGL2"``
as renderer strings, which are not things ``getParameter`` ever returns.

This module now derives stable seeds and plausible GPU strings from the
persona.  Stable matters: recomputing *random* canvas noise per call is itself
a fingerprinting signal, so a persona must always produce the same pixels.
"""

from __future__ import annotations

import hashlib
import json
from typing import Any, Dict, List, Tuple

from fpr.fingerprint import persona_seed

# Real UNMASKED_VENDOR_WEBGL / UNMASKED_RENDERER_WEBGL pairs, per platform.
WEBGL_STRINGS: List[Tuple[str, str]] = [
    ("Google Inc. (NVIDIA)", "ANGLE (NVIDIA, NVIDIA GeForce RTX 3060 Direct3D11 vs_5_0 ps_5_0, D3D11)"),
    ("Google Inc. (Intel)", "ANGLE (Intel, Intel(R) UHD Graphics 630 Direct3D11 vs_5_0 ps_5_0, D3D11)"),
    ("Google Inc. (Apple)", "ANGLE (Apple, ANGLE Metal Renderer: Apple M2, Unspecified Version)"),
    ("Apple Inc.", "Apple GPU"),
]

WGPU_STRINGS: List[str] = [
    "ANGLE (NVIDIA, NVIDIA GeForce RTX 3060 Direct3D11 vs_5_0 ps_5_0, D3D11)",
    "ANGLE (Apple, ANGLE Metal Renderer: Apple M2, Unspecified Version)",
]




def seed_for(profile: Any) -> int:
    """Stable 53-bit seed for a persona (dict, Profile, or partial dict)."""
    if hasattr(profile, "to_dict"):
        profile = profile.to_dict()
    return persona_seed(dict(profile or {}))


def harden(profile: Any) -> Dict[str, Any]:
    """Return the deterministic noise/GPU material for a persona."""
    data = profile.to_dict() if hasattr(profile, "to_dict") else dict(profile or {})
    seed = seed_for(data)

    vendor = data.get("webglVendor") or WEBGL_STRINGS[0][0]
    renderer = data.get("webglRenderer") or WEBGL_STRINGS[0][1]

    # Distinct, stable sub-seeds so canvas and audio do not perturb each other.
    # Prefer the values baked into the persona; fall back to deriving them.
    canvas_seed = int(data.get("canvasSeed") or ((seed ^ 0x5BF03635) & 0xFFFFFFFF))
    audio_seed = int(data.get("audioSeed") or (((seed >> 3) ^ 0x9E3779B9) & 0xFFFFFFFF))

    return {
        "webgl": {"vendor": vendor, "renderer": renderer},
        "wgpu": renderer if renderer in WGPU_STRINGS else WGPU_STRINGS[0],
        "seed": seed,
        "canvasSeed": canvas_seed,
        "audioSeed": audio_seed,
        "stable": hashlib.sha1(
            json.dumps([vendor, renderer, canvas_seed, audio_seed]).encode()
        ).hexdigest()[:16],
    }


if __name__ == "__main__":  # pragma: no cover - manual smoke test
    import random

    from fpr import catalog
    from fpr.fingerprint import gen

    rng = random.Random(99)
    for browser, platform in catalog.combos():
        persona = gen(rng, browser, platform)
        out = harden(persona)
        again = harden(persona)
        assert out == again, "hardening must be deterministic"
        print("%-6s %-8s %s" % (browser, platform, out["webgl"]["renderer"][:64]))
