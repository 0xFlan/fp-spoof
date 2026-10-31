"""Zone offsets to IANA identifiers.

Only zones with NO daylight saving are represented, so the browser-reported
UTC offset equals Profile.zone all year round. A DST zone would make the
probe disagree with the profile for half the year.

tests/test_render.py::test_zone_offsets_are_constant_year_round checks this
against the tz database rather than trusting the comment.
"""

IANA_BY_ZONE = {
    -7: "America/Phoenix",
    -5: "America/Bogota",
    -3: "America/Sao_Paulo",
    0: "Africa/Abidjan",
    1: "Africa/Lagos",
    9: "Asia/Tokyo",
}


def timezone_for(profile) -> str:
    return IANA_BY_ZONE.get(profile.zone, "UTC")
