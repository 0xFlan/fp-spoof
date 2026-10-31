"""Local stand-in for a client-side fingerprinting library.

Everything here is observable from the UA string and the declared profile, so
consistency() answers one narrow question: would a UA parser agree with the
rest of the record? The rendered-browser score is a separate layer that needs
a real browser.

The previous version returned 0.0 for every edge and safari profile because
the generator emitted bare version strings as UAs.
"""
from __future__ import annotations

from fpr.stability import digest


def parse_ua(ua: str):
    """Return (platform, browser) as a detector would see them."""
    ua = ua or ""
    if "iPhone" in ua:
        platform = "ios"
    elif "Windows NT" in ua:
        platform = "windows"
    elif "Macintosh" in ua:
        platform = "mac"
    elif "Linux" in ua:
        platform = "linux"
    else:
        platform = "unknown"

    if "Edg/" in ua:
        browser = "edge"
    elif "Chrome/" in ua:
        browser = "chrome"
    elif "Safari/" in ua:
        browser = "safari"
    else:
        browser = "unknown"

    return platform, browser


def consistency(profile, weights=(1.0, 1.0, 0.5, 0.5)) -> float:
    platform, browser = parse_ua(profile.ua)
    checks = (
        platform == profile.platform,
        browser == profile.browser,
        bool(profile.sensors) == (profile.platform == "ios"),
        bool(profile.plugins) == (profile.browser != "safari"),
    )
    earned = sum(w for w, ok in zip(weights, checks) if ok)
    return round(earned / sum(weights), 3)


def fingerprint(profile) -> str:
    """Visitor-ID analogue: a stable hash of every observable signal."""
    return digest(profile)
