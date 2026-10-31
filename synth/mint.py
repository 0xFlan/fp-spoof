"""Deterministic profile minting.

mint(seed) is a pure function: the same seed always yields an identical
Profile. That invariant is what makes a profile stable across visits, which
is the property detectors actually test (fpr/stability.py).

Fields are drawn in dependency order, so a minted profile cannot contradict
itself:

    cpu -> memory       nothing ships 16 cores with 4 GiB
    screen -> dpr       a 2x display is never 1280 CSS px wide
    language -> zone    an en-US machine is not in Tokyo

fix/reconcile.py re-checks those same relationships, so the two layers
agree: reconcile() can reject a hand-edited record that mint() could never
produce, and never rejects one it did.

Each derived block draws from its own RNG so that adding a field later does
not silently shift every other value.
"""

from __future__ import annotations

import random

from fix.harden import gpu_strings
from models.profile import Profile
from synth import tables


class MintError(ValueError):
    """Raised when a browser/platform pair is not representable."""


def _dpr_choices(platform, screen_x):
    """Device pixel ratios that can plausibly drive a display this wide."""
    return tuple(dpr for dpr in tables.DPR[platform] if dpr < 2 or screen_x >= 1440)


def mint(seed, browser=None, platform="windows", pool="default", name=None):
    if platform not in tables.ALLOWED:
        raise MintError(f"unknown platform: {platform!r}")
    allowed = tables.ALLOWED[platform]
    if browser is None:
        browser = allowed[0]
    if browser not in allowed:
        raise MintError(
            f"{browser!r} cannot run on {platform!r}; allowed: {', '.join(allowed)}"
        )

    seed = int(seed)
    rng = random.Random(seed)

    screen_x, screen_y = rng.choice(tables.SCREENS[platform])

    # CPU before memory: twelve cores or more implies at least 8 GiB.
    cores = rng.choice(tables.CORES[platform])
    if cores >= 12:
        device_memory = max(tables.MEMORY[platform])
    else:
        device_memory = rng.choice(tables.MEMORY[platform])

    dpr = rng.choice(_dpr_choices(platform, screen_x))
    touch = rng.choice(tables.TOUCH[platform])

    # Language before zone, so the two always belong together.
    languages = rng.choice(tables.LANGUAGES)
    zone = rng.choice(tables.LANGUAGE_ZONES[languages[0]])

    chrome_major = rng.choice(tables.CHROME_MAJOR)
    ua = tables.UA_TEMPLATES[(browser, platform)].format(chrome=chrome_major)

    # Independent streams: GPU and canvas are derived from the seed alone, so
    # they can never drift when the field list above changes.
    gpu = gpu_strings(random.Random((seed * 0x9E3779B1) & 0xFFFFFFFF), platform)
    canvas_salt = random.Random((seed * 0x85EBCA6B) & 0xFFFFFFFF).getrandbits(31)

    return Profile(
        seed=seed,
        # The seed belongs in the name. Without it two seeds shared one name,
        # and therefore one user_data_dir and one store row.
        name=name or f"profile-{browser}-{platform}-{seed}",
        pool=pool,
        browser=browser,
        platform=platform,
        ua=ua,
        platformKey=tables.PLATFORM_KEY[platform],
        screenX=int(screen_x),
        screenY=int(screen_y),
        deviceMemory=int(device_memory),
        hardwareConcurrency=int(cores),
        pixelRatio=float(dpr),
        touchPoints=int(touch),
        sensors=False,
        plugins=tuple(tables.PLUGINS_BY_BROWSER[browser]),
        pdfViewer="internal-pdf-viewer",
        java="",
        languagesZ=tuple(languages),
        zone=int(zone),
        wglVendor=gpu["vendor"],
        wglRenderer=gpu["renderer"],
        wgpuAdapter=gpu["adapter"],
        canvasSalt=int(canvas_salt),
    )
