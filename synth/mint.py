"""Deterministic profile minting.

mint(seed) is a pure function: the same seed always yields an identical
Profile. That invariant is what makes a profile stable across visits, which
is the property detectors actually test (fpr/stability.py).

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
    device_memory = rng.choice(tables.MEMORY[platform])
    cores = rng.choice(tables.CORES[platform])
    dpr = rng.choice(tables.DPR[platform])
    touch = rng.choice(tables.TOUCH[platform])
    zone = rng.choice(tables.ZONES[platform])
    languages = rng.choice(tables.LANGUAGES)
    chrome_major = rng.choice(tables.CHROME_MAJOR)
    safari_version = rng.choice(tables.SAFARI_VERSION)

    ua = tables.UA_TEMPLATES[(browser, platform)].format(
        chrome=chrome_major, safari=safari_version
    )

    if browser == "safari":
        plugins = ()
        pdf_viewer = ""
        java = ""
    else:
        plugins = tables.PLUGINS_DESKTOP
        pdf_viewer = "internal-pdf-viewer"
        java = ""

    # Independent streams: GPU and canvas are derived from the seed alone, so
    # they can never drift when the field list above changes.
    gpu = gpu_strings(random.Random((seed * 0x9E3779B1) & 0xFFFFFFFF), platform)
    canvas_salt = random.Random((seed * 0x85EBCA6B) & 0xFFFFFFFF).getrandbits(31)

    return Profile(
        seed=seed,
        name=name or f"profile-{browser}-{platform}",
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
        sensors=(platform == "ios"),
        plugins=tuple(plugins),
        pdfViewer=pdf_viewer,
        java=java,
        languagesZ=tuple(languages),
        zone=int(zone),
        wglVendor=gpu["vendor"],
        wglRenderer=gpu["renderer"],
        wgpuAdapter=gpu["adapter"],
        canvasSalt=int(canvas_salt),
    )
