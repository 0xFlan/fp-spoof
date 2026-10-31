"""HTTP headers implied by a profile.

The UA and the client hints must tell the SAME story: a Chrome UA with no
sec-ch-ua, or a sec-ch-ua-platform of "Windows" behind an Apple GPU, is
trivial to spot. Both are derived from the profile here, and whether the
engine sends hints at all comes from the capability table rather than from
an assumption about what Chromium does.
"""

from __future__ import annotations

import re

from synth import tables

PLATFORM_LABEL = {
    "windows": '"Windows"',
    "mac": '"macOS"',
    "linux": '"Linux"',
}

# Chromium's GREASE brand. The spelling is "Not_A Brand" with an underscore;
# a hyphen here is a value no real browser produces.
GREASE = '"Not_A Brand";v="24"'

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


def brands(profile, major: int) -> list:
    chromium = f'"Chromium";v="{major}"'
    if profile.browser == "edge":
        # Edge advertises itself and Chromium, and never claims to be Chrome.
        return [GREASE, f'"Microsoft Edge";v="{major}"', chromium]
    if profile.browser == "chrome":
        return [GREASE, chromium, f'"Google Chrome";v="{major}"']
    return []


def headers(profile) -> dict:
    out = {
        "user-agent": profile.ua,
        "accept-language": accept_language(profile.languagesZ),
    }
    if not tables.BROWSER_CAPS.get(profile.browser, {}).get("clientHints"):
        return out
    major = major_version(profile.ua)
    out["sec-ch-ua"] = ", ".join(brands(profile, major))
    out["sec-ch-ua-mobile"] = "?0"
    out["sec-ch-ua-platform"] = PLATFORM_LABEL[profile.platform]
    return out
