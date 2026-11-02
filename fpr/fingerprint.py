"""Persona generation and entropy accounting.

Two things were fake in the original build and are real now:

* ``entropy_flat`` returned the *list of candidate memory sizes* rather than a
  number, so ``12.5 * len(...)`` was a constant 50.0 for every profile and the
  entropy floor never rejected anything.
* ``gen`` picked screen width and height independently, so it happily produced
  a 3900x720 window, and it never emitted ``touchPoints`` even though the
  reconciler required it.
"""

from __future__ import annotations

import hashlib
import json
import math
import random
from collections import Counter
from typing import Any, Dict, List, Optional, Sequence

from fpr import catalog, geo as geodata

FREE = ("zOne", "zTwo", "zThree", "zFour")
QUASI = ("deviceMemory", "hardwareConcurrency", "pixelRatio", "screenX", "screenY")


def getplat(p: Dict[str, Any]) -> str:
    return (p or {}).get("platform", "windows")


def _bits(n: int) -> float:
    """Entropy of a uniform choice among ``n`` alternatives."""
    return math.log2(n) if n > 1 else 0.0


def entropy_field(p: Dict[str, Any]) -> Dict[str, float]:
    """Per-field entropy in bits, derived from catalog cardinality.

    Returns a mapping of field name to the number of bits that field
    contributes when it is chosen uniformly from the catalog.
    """
    platform = getplat(p)
    browser = (p or {}).get("browser", "chrome")

    browser_count = len(catalog.browsers())
    platforms = catalog.platforms_for(browser) if browser in catalog.browsers() else []
    os_spec = catalog.os_table().get(platform, {})
    spec = catalog.browsers().get(browser, {})

    langs = catalog.locale()["languages"]
    tz_count = max((len(catalog.locale()["timezones"].get(entry[0], []) or [1]) for entry in langs), default=1)

    out = {
        "browser": _bits(browser_count),
        "platform": _bits(len(platforms)),
        "version": _bits(len(spec.get("versions", []))),
        "screen": _bits(len(catalog.screens_for(platform))),
        "deviceMemory": _bits(len(os_spec.get("mem") or [])),
        "hardwareConcurrency": _bits(len(os_spec.get("conc") or [])),
        "languages": _bits(len(langs)),
        "timezone": _bits(tz_count),
        "gpu": _bits(len(catalog.gpus_for(platform, os_spec.get("architecture", "x86_64")))),
        "zone": _bits(len(os_spec.get("zone") or [])),
    }
    return {k: round(v, 4) for k, v in out.items()}


def entropy_bits(p: Dict[str, Any]) -> float:
    """Total independent entropy of a persona, in bits."""
    return round(sum(entropy_field(p).values()), 4)


def entropy_flat(p: Dict[str, Any]) -> List[int]:
    """Candidate ``deviceMemory`` values for the persona's platform.

    Kept under the original name because callers used it as a lookup, not as an
    entropy measurement.
    """
    platform = getplat(p)
    return list(catalog.os_table().get(platform, {}).get("mem") or [])


def mean_dist(p: Dict[str, Any]) -> float:
    """Mean pairwise field distance between this persona and random siblings.

    The old ``meandist`` returned ``12.5 * len(entropy_flat(p))``, i.e. 50.0
    always.  This actually samples and measures.
    """
    return mean_distance(n=64, browser=(p or {}).get("browser", "chrome"), platform=getplat(p))


def mean_distance(n: int = 64, browser: str = "chrome", platform: str = "windows", seed: int = 0) -> float:
    """Average fraction of fields that differ across ``n`` sampled personas.

    A value near 1.0 means generated profiles are genuinely distinct; near 0.0
    means they are clones.
    """
    rng = random.Random(seed)
    samples = [gen(rng, browser, platform) for _ in range(n)]
    fields = ("version", "screenX", "screenY", "pixelRatio", "deviceMemory",
              "hardwareConcurrency", "languagesZ", "timezone", "webglRenderer", "zone")
    total = 0.0
    pairs = 0
    for i in range(len(samples)):
        for j in range(i + 1, len(samples)):
            a, b = samples[i], samples[j]
            differing = sum(1 for f in fields if a.get(f) != b.get(f))
            total += differing / len(fields)
            pairs += 1
    return round(total / pairs, 4) if pairs else 0.0


def _brand_list(spec: Dict[str, Any], version: str) -> List[Dict[str, str]]:
    """Client-hint brand list for a persona.

    Chrome sends ``Chromium``, the product brand, and the greased
    ``Not_A Brand`` entry, in a per-build shuffled order. The catalog lists the
    real brands; the greased entry and the ordering are added here.
    """
    major = version.split(".")[0]
    names = [str(name) for name in (spec.get("chBrands") or [])]
    if not names:
        return []
    out = [{"brand": name, "version": major} for name in names]
    out.append({"brand": "Not_A Brand", "version": "24"})
    order = sorted(names)
    out.sort(key=lambda item: order.index(item["brand"]) if item["brand"] in order else len(order))
    return out


def gen(
    rng: random.Random,
    browser: str = "chrome",
    platform: str = "windows",
    version: Optional[str] = None,
) -> Dict[str, Any]:
    """Build one coherent persona.

    Every field is drawn from the catalog, and cross-field relationships are
    enforced by construction (touch points follow the platform, Safari has no
    ``deviceMemory``, the GPU matches the architecture, the timezone matches the
    language, and so on).
    """
    spec = catalog.browser(browser)
    if platform not in spec["platforms"]:
        raise ValueError(
            "browser %r is not available on %r; supported: %s"
            % (browser, platform, ", ".join(spec["platforms"]))
        )
    os_spec = catalog.platform(platform)

    version = version or rng.choice(spec["versions"])
    ua = spec["ua"][platform].format(version=version)

    width, height, dpr = rng.choice(catalog.screens_for(platform))
    width, height = int(width), int(height)

    architecture = os_spec["architecture"]
    memory_choices = os_spec.get("mem") or []
    device_memory = int(rng.choice(memory_choices)) if (memory_choices and spec["supportsDeviceMemory"]) else None

    gpu = rng.choice(catalog.gpus_for(platform, architecture))
    languages = list(rng.choice(catalog.locale()["languages"]))
    timezones = catalog.locale()["timezones"].get(languages[0]) or ["UTC"]
    timezone = rng.choice(timezones)

    persona = {
        "browser": browser,
        "platform": platform,
        "version": version,
        "platformKey": os_spec["platformKey"],
        "architecture": architecture,
        "screenX": width,
        "screenY": height,
        "availX": width,
        "availY": max(0, height - int(os_spec.get("availInsetY", 0))),
        "deviceMemory": device_memory,
        "hardwareConcurrency": int(rng.choice(os_spec["conc"])),
        "pixelRatio": float(dpr),
        "colorDepth": 24,
        "maxTouchPoints": int(os_spec.get("maxTouchPoints", 0)) if "maxTouchPoints" in os_spec else (5 if platform == "ios" else 0),
        "languagesZ": languages,
        "timezone": timezone,
        # Location is part of the identity, not a free-floating number:
        # the coordinates are the timezone's city, so geolocation agrees.
        "geo": geodata.geo_for(timezone),
        "connection": {
            "effectiveType": "4g",
            "downlink": float(rng.choice([10.0, 9.5, 8.0])),
            "rtt": int(rng.choice([50, 100])),
            "saveData": False,
        },
        # ICE host candidates leak the real LAN address even when every
        # other value is spoofed, so they are filtered by default.
        "webrtcPolicy": "filter",
        "proxy": None,
        "sensors": bool(spec["sensors"]),
        "ua": ua,
        "vendor": spec["vendor"],
        "webglVendor": gpu["vendor"],
        "webglRenderer": gpu["renderer"],
        "plugins": tuple(spec["plugins"]),
        "pdfViewer": spec["plugins"][0] if spec["plugins"] else "",
        "java": "" if browser == "safari" else "11.0.2",
        "zone": int(rng.choice(os_spec["zone"])),
        "userAgentData": {
            "brands": _brand_list(spec, version),
            "mobile": platform == "ios",
            "platform": platform,
            "architecture": os_spec.get("archCh", "x86"),
            "bitness": "64",
            "platformVersion": rng.choice(os_spec.get("platformVersion", ["10.0.0"])),
            "uaFullVersion": version,
        },
        "seed": rng.getrandbits(53),
    }
    persona["touchPoints"] = persona["maxTouchPoints"]

    # Stable per-persona noise seeds. Derived here (not in the JS) so the
    # extension and the launcher perturb canvases identically.
    base = persona_seed(persona)
    persona["canvasSeed"] = (base ^ 0x5BF03635) & 0xFFFFFFFF
    persona["audioSeed"] = ((base >> 3) ^ 0x9E3779B9) & 0xFFFFFFFF
    return persona


def make(rng: random.Random, browser: str = "chrome", platform: str = "windows") -> Dict[str, Any]:
    return gen(rng, browser, platform)


def persona_seed(p: Dict[str, Any]) -> int:
    """Stable 53-bit seed for a persona.

    Used for canvas/audio noise so the same persona always produces the same
    perturbed pixels. Random-per-call noise is itself a detection signal, which
    is why the old build's approach was wrong in principle, not just buggy.
    """
    payload = {k: v for k, v in sorted((p or {}).items()) if k not in ("seed", "name")}
    digest = hashlib.sha256(json.dumps(payload, sort_keys=True, default=str).encode("utf-8")).digest()
    return int.from_bytes(digest[:7], "big")


def entropy_floor(p: Dict[str, Any], dist: Optional[Dict[str, float]] = None):
    """``(ok, bits, reason)`` against a minimum-entropy threshold."""
    threshold = float((dist or {}).get("min", catalog.load().get("minEntropyBits", 24.0)))
    bits = entropy_bits(p)
    if bits < threshold:
        return False, bits, "low-entropy"
    return True, bits, None


if __name__ == "__main__":  # pragma: no cover - manual smoke test
    r = random.Random(7)
    for browser in catalog.browsers():
        for platform in catalog.platforms_for(browser):
            p = make(r, browser, platform)
            print("%-6s %-8s %5dx%-5d dpr %.1f mem %-4s cores %-2d tz %-18s %s"
                  % (browser, platform, p["screenX"], p["screenY"], p["pixelRatio"],
                     p["deviceMemory"], p["hardwareConcurrency"], p["timezone"], p["ua"][:52]))
