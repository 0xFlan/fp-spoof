"""Renderer tests that need no browser."""

from datetime import datetime, timezone
from zoneinfo import ZoneInfo

from render.inject import PROFILE_TOKEN, init_script, payload
from render.timezones import IANA_BY_ZONE
from synth import tables
from synth.mint import mint
from verify.browser_probe import diff


def test_init_script_embeds_the_profile():
    profile = mint(111)
    script = init_script(profile)
    assert PROFILE_TOKEN not in script
    assert profile.wglRenderer in script
    assert str(profile.hardwareConcurrency) in script


def test_init_script_is_stable_for_one_seed():
    assert init_script(mint(111)) == init_script(mint(111))


def test_init_script_differs_between_seeds():
    assert init_script(mint(111)) != init_script(mint(112))


def test_payload_carries_the_engine_capabilities():
    profile = mint(111, "edge", "windows")
    assert payload(profile)["caps"] == tables.BROWSER_CAPS["edge"]


def test_device_memory_is_defined_inside_a_capability_guard():
    script = init_script(mint(111, "chrome", "windows"))
    guarded = script.split("if (P.caps.deviceMemory) {", 1)[1]
    assert "'deviceMemory'" in guarded.split("}", 1)[0]


def test_properties_are_defined_on_the_prototype_not_the_instance():
    # A real browser exposes these as inherited getters, so an own property
    # on the instance is a tell even when the value is right.
    script = init_script(mint(111, "chrome", "windows"))
    for name in ("hardwareConcurrency", "platform", "languages", "plugins"):
        assert f"navigatorProto, navigator, '{name}'" in script
    assert "define(navigator, '" not in script


def test_patched_functions_are_disguised_as_native():
    script = init_script(mint(111, "chrome", "windows"))
    assert "disguised.push(patched);" in script
    assert "[native code]" in script


def test_diff_is_clean_when_the_page_matches():
    profile = mint(7, "chrome", "windows")
    assert diff(profile, payload(profile)) == []


def test_diff_reports_exactly_the_tampered_field():
    profile = mint(7, "chrome", "windows")
    observed = dict(payload(profile))
    observed["cores"] = 999
    problems = diff(profile, observed)
    assert [problem["field"] for problem in problems] == ["cores"]
    assert problems[0]["expected"] == profile.hardwareConcurrency


def test_diff_requires_an_unsupported_property_to_be_absent():
    profile = mint(7, "chrome", "windows")
    observed = dict(payload(profile))
    caps = {"deviceMemory": False}
    problems = diff(profile, observed, caps=caps)
    assert [problem["field"] for problem in problems] == ["memory"]
    assert problems[0]["expected"] is None
    observed["memory"] = None
    assert diff(profile, observed, caps=caps) == []


def test_every_zone_has_a_dst_free_timezone():
    for zones in tables.ZONES.values():
        for zone in zones:
            assert zone in IANA_BY_ZONE


def test_zone_offsets_are_constant_year_round():
    for zone, name in IANA_BY_ZONE.items():
        tzinfo = ZoneInfo(name)
        for month in (1, 7):
            moment = datetime(2026, month, 15, 12, tzinfo=timezone.utc)
            offset = moment.astimezone(tzinfo).utcoffset().total_seconds() / 3600
            assert offset == zone, (name, month, offset)
