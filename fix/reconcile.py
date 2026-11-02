"""Cross-field consistency checks.

Every rule here is derived from the catalog.  The previous version kept a
second, contradictory rule table (it demanded ``x86_64`` for mac in
``models/profile.py`` while ``reconcile.py`` accepted ``amd64``), so a profile
could be valid and invalid at the same time depending on which module you
asked.  It also read ``p["touchPoints"]``, which generation never emitted, so
every Safari profile raised ``KeyError``.
"""

from __future__ import annotations

from typing import Any, Dict, List

from fpr import catalog, geo as geodata
from fpr import net
from models.profile import constraint

ARCH_ALIASES = {"x86_64", "amd64", "x64", "arm64", "aarch64"}


def _normalise(profile: Any) -> Dict[str, Any]:
    if profile is None:
        return {}
    if hasattr(profile, "to_dict"):
        return profile.to_dict()
    if isinstance(profile, dict):
        return dict(profile)
    raise TypeError("reconcile() expects a Profile or dict, got %r" % (type(profile).__name__,))


def reconcile(profile: Any) -> List[str]:
    """Return a sorted list of consistency error codes. Empty means valid."""
    data = _normalise(profile)
    errors: set = set()

    browser = str(data.get("browser") or "")
    platform = str(data.get("platform") or "")

    browsers = catalog.browsers()
    os_table = catalog.os_table()
    if browser not in browsers:
        return ["unknown-browser"]
    if platform not in os_table:
        return ["unknown-platform"]

    spec = browsers[browser]
    os_spec = os_table[platform]
    rules = constraint(browser)

    # --- platform / browser combination -----------------------------------
    if platform not in spec["platforms"]:
        errors.add("unsupported-combo")

    # --- user agent -------------------------------------------------------
    ua = str(data.get("ua") or "")
    if not ua:
        errors.add("ua-missing")
    else:
        if spec["browserToken"] not in ua:
            errors.add("ua-browser-token")
        expected_token = (spec.get("uaPlatformToken") or {}).get(platform)
        if expected_token and expected_token not in ua:
            errors.add("ua-platform-token")
        version = str(data.get("version") or "")
        if version and version not in ua:
            errors.add("ua-version-mismatch")
        if "HeadlessChrome" in ua:
            errors.add("ua-headless")
        if "Mobile" in ua and platform != "ios":
            errors.add("ua-mobile-desktop")

    # --- platform identity ------------------------------------------------
    if data.get("platformKey") and data.get("platformKey") != os_spec["platformKey"]:
        errors.add("platformkey-mismatch")

    architecture = str(data.get("architecture") or "")
    if architecture and architecture not in ARCH_ALIASES:
        errors.add("arch-unknown")
    elif platform == "mac":
        if architecture and architecture not in ("arm64", "x86_64"):
            errors.add("arch-mismatch")
    elif architecture and architecture != os_spec["architecture"]:
        errors.add("arch-mismatch")

    # --- capability flags -------------------------------------------------
    if bool(data.get("sensors")) != bool(rules["sensors"]):
        errors.add("sensors-mismatch")

    plugins = tuple(data.get("plugins") or ())
    if plugins and plugins != tuple(rules["plugins"]):
        errors.add("plugins-mismatch")

    expected_touch = 5 if platform == "ios" else 0
    touch = data.get("maxTouchPoints", data.get("touchPoints"))
    if touch is None:
        errors.add("touchpoints-missing")
    elif int(touch) != expected_touch:
        errors.add("touchpoints-mismatch")

    # --- hardware ---------------------------------------------------------
    memory = data.get("deviceMemory")
    if not rules["supportsDeviceMemory"]:
        if memory is not None:
            errors.add("memory-unsupported")
    else:
        if memory is None:
            errors.add("memory-missing")
        elif int(memory) not in (os_spec.get("mem") or []):
            errors.add("memory-out-of-range")

    cores = data.get("hardwareConcurrency")
    if cores is None:
        errors.add("cores-missing")
    elif int(cores) not in (os_spec.get("conc") or []):
        errors.add("cores-out-of-range")

    # --- screen -----------------------------------------------------------
    width, height = data.get("screenX"), data.get("screenY")
    dpr = data.get("pixelRatio")
    if width is None or height is None:
        errors.add("screen-missing")
    else:
        known = {(int(w), int(h), float(d)) for w, h, d in catalog.screens_for(platform)}
        try:
            key = (int(width), int(height), float(dpr))
        except (TypeError, ValueError):
            errors.add("screen-incoherent")
            key = None
        if key is not None and key not in known:
            errors.add("screen-incoherent")

    avail_x, avail_y = data.get("availX"), data.get("availY")
    if width is not None and avail_x is not None and int(avail_x) > int(width):
        errors.add("avail-exceeds-screen")
    if height is not None and avail_y is not None and int(avail_y) > int(height):
        errors.add("avail-exceeds-screen")

    if dpr is None:
        errors.add("dpr-invalid")
    else:
        try:
            if float(dpr) <= 0 or float(dpr) > 4:
                errors.add("dpr-invalid")
        except (TypeError, ValueError):
            errors.add("dpr-invalid")

    if data.get("colorDepth") not in (None, 24):
        errors.add("colordepth")

    # --- locale -----------------------------------------------------------
    languages = data.get("languagesZ") or []
    if not languages:
        errors.add("languages-empty")
    else:
        primary = str(languages[0])
        allowed = catalog.locale()["timezones"].get(primary)
        timezone = str(data.get("timezone") or "")
        if allowed is None:
            errors.add("language-unknown")
        elif timezone not in allowed:
            errors.add("timezone-locale-mismatch")

    # --- location ---------------------------------------------------------
    errors.update(geodata.check(data))

    # --- proxy ------------------------------------------------------------
    errors.update(net.problems(data.get("proxy")))

    # --- GPU --------------------------------------------------------------
    gpu_vendor = str(data.get("webglVendor") or "")
    gpu_renderer = str(data.get("webglRenderer") or "")
    if not gpu_vendor or not gpu_renderer:
        errors.add("webgl-missing")
    else:
        pairs = {(g["vendor"], g["renderer"]) for g in catalog.gpus_for(platform, architecture or os_spec["architecture"])}
        if pairs and (gpu_vendor, gpu_renderer) not in pairs:
            errors.add("webgl-implausible")

    # --- OS version -------------------------------------------------------
    zone = data.get("zone")
    if zone is None:
        errors.add("zone-missing")
    elif int(zone) not in (os_spec.get("zone") or []):
        errors.add("zone-out-of-range")

    return sorted(errors)


def is_valid(profile: Any) -> bool:
    """True when the profile has no consistency errors."""
    return not reconcile(profile)


def describe(profile: Any) -> str:
    """Human-readable summary of problems, or ``"ok"``."""
    problems = reconcile(profile)
    return "ok" if not problems else ", ".join(problems)
