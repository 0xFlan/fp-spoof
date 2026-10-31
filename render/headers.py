"""HTTP headers implied by a profile.

The UA and the client hints must tell the SAME story: a Chrome UA with no
sec-ch-ua, or a sec-ch-ua-platform of "Windows" behind an Apple GPU, is
trivial to spot. Both are derived from the profile here.
"""
from __future__ import annotations

import re

PLATFORM_LABEL = {
    "windows": '"Windows"',
    "mac": '"macOS"',
    "linux": '"Linux"',
    "ios": '"iOS"',
}

_MAJOR = re.compile(r"(?:Chrome|Edg)/(\d+)")


def major_version(ua: str) -> int:
    found = _MAJOR.search(ua or "")
    return int(found.group(1)) if found else 0


def accept_language(languages) -> str:
    parts = []
    for index, language in enumerate(languages):
        if index == 0:
            parts.append(language)
        else:
            weight = max(0.1, 1.0 - index / 10.0)
            parts.append(f"{language};q={weight:.1f}")
    return ",".join(parts)


def headers(profile) -> dict:
    ua = profile.ua
    out = {
        "user-agent": ua,
        "accept-language": accept_language(profile.languagesZ),
    }

    if profile.browser not in ("chrome", "edge"):
        return out

    major = major_version(ua)
    brands = [
        f'"Chromium";v="{major}"',
        f'"Google Chrome";v="{major}"',
        '"Not-A.Brand";v="24"',
    ]
    if profile.browser == "edge":
        brands.insert(1, f'"Microsoft Edge";v="{major}"')

    out["sec-ch-ua"] = ", ".join(brands)
    out["sec-ch-ua-mobile"] = "?1" if profile.platform == "ios" else "?0"
    out["sec-ch-ua-platform"] = PLATFORM_LABEL[profile.platform]
    return out
