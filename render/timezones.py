"""Zone offsets to IANA identifiers.

Only zones with NO daylight saving are represented, so the browser-reported
UTC offset equals Profile.zone all year round. A DST zone would make the
probe disagree with the profile for half the year.
"""

IANA_BY_ZONE = {
    9: "Asia/Tokyo",
    10: "Australia/Brisbane",
    11: "Pacific/Noumea",
}


def timezone_for(profile) -> str:
    return IANA_BY_ZONE.get(profile.zone, "UTC")
