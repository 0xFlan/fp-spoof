"""Cross-field consistency checks.

reconcile() NEVER raises: it returns a list of violation codes. A validator
that throws on a partial record cannot be used to reject bad input, only to
crash on it -- which is exactly what the previous version did on every safari
profile, because it read p["touchPoints"] that the generator never emitted.

Accepts either a Profile or a plain mapping, so stored payloads can be
re-validated without reconstructing the dataclass.
"""
from __future__ import annotations

from collections.abc import Mapping

from synth import tables


def _get(record, key, default=None):
    if isinstance(record, Mapping):
        return record.get(key, default)
    return getattr(record, key, default)


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
    if browser not in ("chrome", "edge") and "Chrome/" in ua:
        errors.append("ua-chrome-token")
    if platform == "ios" and "Mobile/" not in ua:
        errors.append("ua-mobile")

    if _get(record, "deviceMemory") not in tables.MEMORY[platform]:
        errors.append("deviceMemory")
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

    if bool(_get(record, "sensors")) != (platform == "ios"):
        errors.append("sensors")
    if _get(record, "touchPoints") not in tables.TOUCH[platform]:
        errors.append("touchPoints")

    plugins = _get(record, "plugins")
    if browser == "safari" and plugins:
        errors.append("safari-plugins")
    if browser != "safari" and not plugins:
        errors.append("missing-plugins")

    if not _get(record, "wglRenderer") or not _get(record, "wgpuAdapter"):
        errors.append("gpu-strings")

    return errors


def is_valid(record) -> bool:
    return not reconcile(record)
