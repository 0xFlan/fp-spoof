"""User-agent parsing and a graded coherence score.

Despite the module name this was never FingerprintJS; it is a self-consistency
scorer.  The old version scored 0.0 for every Edge and Safari persona because
the catalog held UA *fragments* ("183.0.3984.51") rather than user agents, and
it subtracted a full 1.0 per mismatch from a starting score of 1.0, so there
was no middle ground.
"""

from __future__ import annotations

import re
from typing import Any, Dict, Optional

_IOS = re.compile(r"iPhone|iPad|iPod")
_MAC = re.compile(r"Macintosh|Mac OS X")
_WIN = re.compile(r"Windows NT")
_LINUX = re.compile(r"Linux|X11")
_EDGE = re.compile(r"Edg/([\d.]+)")
_CHROME = re.compile(r"Chrome/([\d.]+)")
_SAFARI = re.compile(r"Version/([\d.]+)")
_FIREFOX = re.compile(r"Firefox/([\d.]+)")

# Weights sum to 1.0 so the score is directly interpretable.
WEIGHTS = {
    "platform": 0.30,
    "browser": 0.25,
    "version": 0.15,
    "sensors": 0.15,
    "capabilities": 0.15,
}


def detect_platform(ua: str) -> str:
    ua = ua or ""
    if _IOS.search(ua):
        return "ios"
    if _WIN.search(ua):
        return "windows"
    if _MAC.search(ua):
        return "mac"
    if _LINUX.search(ua):
        return "linux"
    return "unknown"


def detect_browser(ua: str) -> str:
    ua = ua or ""
    if _EDGE.search(ua):
        return "edge"
    if _FIREFOX.search(ua):
        return "firefox"
    if _CHROME.search(ua):
        return "chrome"
    if _SAFARI.search(ua) and "Safari/" in ua:
        return "safari"
    return "unknown"


def detect_version(ua: str) -> str:
    """Full version token for the detected browser, or ``""``."""
    ua = ua or ""
    for pattern in (_EDGE, _CHROME, _FIREFOX, _SAFARI):
        match = pattern.search(ua)
        if match:
            return match.group(1)
    return ""


def browser_version(profile: Any) -> str:
    data = profile.to_dict() if hasattr(profile, "to_dict") else dict(profile or {})
    version = str(data.get("version") or "")
    if version:
        return version
    return detect_version(str(data.get("ua") or ""))


def fingerprint(profile: Any) -> float:
    """Consistency score in ``[0.0, 1.0]``.

    ``1.0`` means the profile's declared identity is exactly what its own user
    agent claims, and its capability flags match that browser.
    """
    data = profile.to_dict() if hasattr(profile, "to_dict") else dict(profile or {})
    ua = str(data.get("ua") or "")
    if not ua:
        return 0.0

    score = 0.0

    declared_platform = str(data.get("platform") or "")
    if detect_platform(ua) == declared_platform:
        score += WEIGHTS["platform"]

    declared_browser = str(data.get("browser") or "")
    if detect_browser(ua) == declared_browser:
        score += WEIGHTS["browser"]

    declared_version = str(data.get("version") or "")
    if not declared_version:
        score += WEIGHTS["version"]
    elif declared_version in ua:
        score += WEIGHTS["version"]
    elif declared_version.split(".")[0] == detect_version(ua).split(".")[0]:
        score += WEIGHTS["version"] * 0.5

    # Safari is the only one of our browsers that exposes motion sensors, and
    # the only one that does not expose navigator.deviceMemory.
    sensors_ok = bool(data.get("sensors")) == (declared_browser == "safari")
    if sensors_ok:
        score += WEIGHTS["sensors"]

    touch = int(data.get("maxTouchPoints", data.get("touchPoints", 0)) or 0)
    plugins = tuple(data.get("plugins") or ())
    memory = data.get("deviceMemory")
    caps_ok = True
    if declared_platform == "ios":
        caps_ok = caps_ok and touch > 0
    else:
        caps_ok = caps_ok and touch == 0
    if declared_browser == "safari":
        caps_ok = caps_ok and not plugins and memory is None
    else:
        caps_ok = caps_ok and bool(plugins) and memory is not None
    if caps_ok:
        score += WEIGHTS["capabilities"]

    return round(min(1.0, max(0.0, score)), 4)


def explain(profile: Any) -> Dict[str, Any]:
    """Score plus the individual signals, for ``fps validate --json``."""
    data = profile.to_dict() if hasattr(profile, "to_dict") else dict(profile or {})
    ua = str(data.get("ua") or "")
    return {
        "score": fingerprint(data),
        "ua_platform": detect_platform(ua),
        "ua_browser": detect_browser(ua),
        "ua_version": detect_version(ua),
        "declared_platform": data.get("platform"),
        "declared_browser": data.get("browser"),
        "declared_version": data.get("version"),
    }


def version_major(version: Optional[str]) -> Optional[int]:
    if not version:
        return None
    head = str(version).split(".")[0]
    return int(head) if head.isdigit() else None
