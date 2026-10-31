"""Profile record.

A profile is an IMMUTABLE bundle of the signals a page can read. Every field
must be identical across visits for a given profile (see fpr/stability.py) and
must vary between profiles (see fpr/entropy.py).

`seed` is the only state needed to re-mint an identical profile.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass


@dataclass(frozen=True)
class Profile:
    seed: int
    name: str
    pool: str
    browser: str
    platform: str
    ua: str
    platformKey: str
    screenX: int
    screenY: int
    deviceMemory: int
    hardwareConcurrency: int
    pixelRatio: float
    touchPoints: int
    sensors: bool
    # Immutable defaults only: dataclasses reject list/dict defaults.
    plugins: tuple = ()
    pdfViewer: str = ""
    java: str = ""
    languagesZ: tuple = ("en-US", "en")
    zone: int = 10
    wglVendor: str = ""
    wglRenderer: str = ""
    wgpuAdapter: str = ""
    canvasSalt: int = 0

    def to_dict(self) -> dict:
        return asdict(self)
