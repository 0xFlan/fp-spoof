"""Cross-field consistency checks.

reconcile() NEVER raises: it returns a list of violation codes. A validator
that throws on a partial record cannot be used to reject bad input, only to
crash on it -- which is exactly what the previous version did on every safari
profile, because it read p["touchPoints"] that the generator never emitted.

Accepts either a Profile or a plain mapping, so stored payloads can be
re-validated without reconstructing the dataclass.

Membership checks prove each value legal on its own. The relationship checks
at the bottom prove the combination is a machine someone could own.
"""

from __future__ import annotations

from collections.abc import Mapping

from synth import tables


def _get(record, key, default=None):
    if isinstance(record, Mapping):
        return record.get(key, default)
    return getattr(record, key, default)


def _num(record, key):
    """Numeric value of a field, or None when absent or not a number."""
    value = _get(record, key)
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return value


def reconcile(record) -> list:
    errors = []
    platform = _get(record, "platform")
    browser = _get(record, "browser")
    ua = _get(record, "ua", "") or ""

    if platform not in tables.ALLOWED:
        # Every remaining check depends on platform; stop here rather than
        # emitting a cascade of derived errors.
        return [f"unknown-platform:{platform!r}"]

    if browser not in tables.ALLOWED[platform]:
        errors.append(f"browser-platform:{browser!r}@{platform!r}")

    platform_token = tables.PLATFORM_TOKENS.get(platform)
    browser_token = tables.BROWSER_TOKENS.get(browser)
    if platform_token and platform_token not in ua:
        errors.append(f"ua-platform:{platform_token}")
    if browser_token and browser_token not in ua:
        errors.append(f"ua-browser:{browser_token}")

    # Exclusivity: a UA must not carry a token for a browser it is not.
    if browser != "edge" and "Edg/" in ua:
        errors.append("ua-edge-token")

    caps = tables.BROWSER_CAPS.get(browser, {})
    if caps.get("deviceMemory"):
        if _get(record, "deviceMemory") not in tables.MEMORY[platform]:
            errors.append("deviceMemory")
    elif _get(record, "deviceMemory") is not None:
        errors.append("deviceMemory-unsupported")

    if _get(record, "hardwareConcurrency") not in tables.CORES[platform]:
        errors.append("hardwareConcurrency")
    if _get(record, "pixelRatio") not in tables.DPR[platform]:
        errors.append("pixelRatio")
    if (_get(record, "screenX"), _get(record, "screenY")) not in tables.SCREENS[platform]:
        errors.append("screen")
    if _get(record, "zone") not in tables.ZONES[platform]:
        errors.append("zone")
    if _get(record, "platformKey") != tables.PLATFORM_KEY[platform]:
        errors.append("platformKey")
    if bool(_get(record, "sensors")):
        errors.append("sensors")
    if _get(record, "touchPoints") not in tables.TOUCH[platform]:
        errors.append("touchPoints")

    # Chromium's plugin list is a property of the browser, not of the machine
    # or the seed, so an inexact set is a rendering bug even when it is a
    # plausible-looking set.
    expected_plugins = tables.PLUGINS_BY_BROWSER.get(browser)
    if expected_plugins is None:
        errors.append(f"plugins-unknown:{browser!r}")
    elif sorted(_get(record, "plugins") or ()) != sorted(expected_plugins):
        errors.append("plugin-set")

    dpr = _num(record, "pixelRatio")
    screen_x = _num(record, "screenX")
    if dpr is not None and screen_x is not None and dpr >= 2 and screen_x < 1440:
        errors.append("screen-vs-dpr")

    cores = _num(record, "hardwareConcurrency")
    memory = _num(record, "deviceMemory")
    if cores is not None and memory is not None and cores >= 12 and memory <= 4:
        errors.append("cores-vs-memory")

    languages = _get(record, "languagesZ") or ()
    language = languages[0] if languages else None
    allowed_zones = tables.LANGUAGE_ZONES.get(language)
    if allowed_zones is None:
        errors.append(f"language-unknown:{language!r}")
    elif _get(record, "zone") not in allowed_zones:
        errors.append(f"zone-vs-language:{language}@{_get(record, 'zone')}")

    if not _get(record, "wglVendor") or not _get(record, "wgpuAdapter"):
        errors.append("gpu-strings")

    return errors


def is_valid(record) -> bool:
    return not reconcile(record)
