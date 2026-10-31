"""Within-profile invariance.

A profile must render identically on every visit. digest() hashes exactly the
fields a detector can observe, so:

    digest(mint(seed)) == digest(mint(seed))     # stable
    digest(mint(a))    != digest(mint(b))         # varied

is the whole stability contract, and it is testable without a browser.
"""
from __future__ import annotations

import hashlib
import json

STABLE_FIELDS = (
    "browser",
    "platform",
    "ua",
    "platformKey",
    "screenX",
    "screenY",
    "deviceMemory",
    "hardwareConcurrency",
    "pixelRatio",
    "touchPoints",
    "sensors",
    "plugins",
    "pdfViewer",
    "java",
    "languagesZ",
    "zone",
    "wglVendor",
    "wglRenderer",
    "wgpuAdapter",
    "canvasSalt",
)


def snapshot(profile) -> dict:
    return {field: getattr(profile, field) for field in STABLE_FIELDS}


def digest(profile) -> str:
    blob = json.dumps(snapshot(profile), sort_keys=True, default=str)
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()[:16]
