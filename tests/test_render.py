"""Renderer tests that need no browser."""
from render.headers import accept_language, headers, major_version
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


def test_chromium_sends_client_hints():
    profile = mint(111, "chrome", "windows")
    result = headers(profile)
    assert result["user-agent"] == profile.ua
    assert result["sec-ch-ua-platform"] == '"Windows"'
    assert result["sec-ch-ua-mobile"] == "?0"


def test_edge_brand_is_present():
    result = headers(mint(111, "edge", "windows"))
    assert "Microsoft Edge" in result["sec-ch-ua"]


def test_safari_sends_no_client_hints():
    result = headers(mint(111, "safari", "mac"))
    assert "sec-ch-ua" not in result


def test_major_version_matches_the_ua():
    profile = mint(111, "chrome", "linux")
    assert f"Chrome/{major_version(profile.ua)}" in profile.ua


def test_accept_language_orders_by_weight():
    assert accept_language(("en-US", "en")) == "en-US,en;q=0.9"


def test_every_zone_has_a_dst_free_timezone():
    for zones in tables.ZONES.values():
        for zone in zones:
            assert zone in IANA_BY_ZONE


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
