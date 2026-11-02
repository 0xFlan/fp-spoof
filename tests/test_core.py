"""Generation, entropy and validation tests."""

import random

import pytest

from api.run import generate, make_profile, probe_profile
from fix.harden import harden
from fix.reconcile import is_valid, reconcile
from fpr import catalog, geo as geodata
from fpr.fingerprint import (
    entropy_bits,
    entropy_field,
    entropy_floor,
    gen,
    mean_distance,
    persona_seed,
)
from models.profile import Profile
from verify.fingerprintjs_vX import detect_browser, detect_platform, fingerprint
from verify.score import score

COMBOS = catalog.combos()


@pytest.mark.parametrize("browser,platform", COMBOS)
def test_generated_personas_are_consistent(browser, platform):
    rng = random.Random(2024)
    for _ in range(20):
        persona = gen(rng, browser, platform)
        assert reconcile(persona) == [], (browser, platform, reconcile(persona))


@pytest.mark.parametrize("browser,platform", COMBOS)
def test_coherence_score_is_perfect(browser, platform):
    persona = gen(random.Random(7), browser, platform)
    assert fingerprint(persona) == 1.0
    ok, details = score(persona)
    assert ok, details


@pytest.mark.parametrize("browser,platform", COMBOS)
def test_screen_and_touch_follow_platform(browser, platform):
    persona = gen(random.Random(3), browser, platform)
    known = {(int(w), int(h), float(d)) for w, h, d in catalog.screens_for(platform)}
    assert (persona["screenX"], persona["screenY"], persona["pixelRatio"]) in known
    assert persona["availY"] <= persona["screenY"]
    assert persona["maxTouchPoints"] == (5 if platform == "ios" else 0)


@pytest.mark.parametrize("browser,platform", COMBOS)
def test_device_memory_matches_browser_capability(browser, platform):
    persona = gen(random.Random(5), browser, platform)
    supports = catalog.browser(browser)["supportsDeviceMemory"]
    assert (persona["deviceMemory"] is None) is (not supports)


def test_every_catalog_timezone_has_a_city():
    """A zone the generator can pick must have coordinates, or geolocation lies."""
    zones = {zone for zones in catalog.locale()["timezones"].values() for zone in zones}
    missing = sorted(zone for zone in zones if not geodata.city(zone))
    assert not missing, missing


def test_generated_personas_carry_location_for_their_own_timezone():
    for browser, platform in COMBOS:
        persona = gen(random.Random(4), browser, platform)
        entry = geodata.city(persona["timezone"])
        assert entry, persona["timezone"]
        assert persona["geo"]["latitude"] == pytest.approx(entry["latitude"], abs=1e-6)
        assert persona["geo"]["longitude"] == pytest.approx(entry["longitude"], abs=1e-6)
        assert geodata.check(persona) == []


def test_nearest_city_round_trips():
    zone, entry, span = geodata.nearest(48.8566, 2.3522)
    assert zone == "Europe/Paris"
    assert span < 5
    assert entry["city"] == "Paris"


def test_reconcile_catches_coordinates_far_from_the_timezone():
    persona = gen(random.Random(9), "chrome", "windows")
    persona["geo"] = dict(persona["geo"], latitude=35.6895, longitude=139.6917)
    if persona["timezone"] != "Asia/Tokyo":
        assert "geo-timezone-mismatch" in reconcile(persona)


def test_reconcile_catches_an_impossible_proxy():
    persona = gen(random.Random(9), "chrome", "windows")
    persona["proxy"] = {"scheme": "gopher", "host": " ", "port": 0}
    problems = reconcile(persona)
    assert {"proxy-scheme", "proxy-host", "proxy-port"} <= set(problems)


def test_proxy_flags_are_the_only_egress_control():
    """The launcher cannot fake an IP, so the flags must be explicit and correct."""
    from launcher.launch import proxy_args

    assert proxy_args(None) == []
    assert proxy_args({}) == []
    flags = proxy_args({"scheme": "socks5", "host": "127.0.0.1", "port": 1080})
    assert "--proxy-server=socks5://127.0.0.1:1080" in flags
    assert "--force-webrtc-ip-handling-policy=disable_non_proxied_udp" in flags


def test_generation_is_deterministic():
    first = gen(random.Random(42), "chrome", "windows")
    second = gen(random.Random(42), "chrome", "windows")
    assert first == second


def test_every_supported_combo_has_a_browser_platform_pair():
    assert COMBOS
    for browser, platform in COMBOS:
        assert platform in catalog.browsers()[browser]["platforms"]


def test_unsupported_combo_is_rejected():
    with pytest.raises(ValueError):
        gen(random.Random(1), "safari", "windows")


def test_entropy_is_not_a_constant():
    """The old build returned 50.0 bits for every single profile."""
    desktop = entropy_bits(gen(random.Random(1), "chrome", "windows"))
    mobile = entropy_bits(gen(random.Random(1), "safari", "ios"))
    assert desktop != mobile
    assert desktop > mobile > 0


def test_entropy_fields_add_up():
    persona = gen(random.Random(2), "chrome", "windows")
    fields = entropy_field(persona)
    assert set(fields) == {
        "browser", "platform", "version", "screen", "deviceMemory",
        "hardwareConcurrency", "languages", "timezone", "gpu", "zone",
    }
    assert all(value >= 0 for value in fields.values())
    assert round(sum(fields.values()), 4) == entropy_bits(persona)


def test_entropy_floor_rejects_low_entropy():
    persona = gen(random.Random(1), "safari", "ios")
    ok, bits, reason = entropy_floor(persona, {"min": bits_needed(persona)})
    assert ok is False
    assert reason == "low-entropy"


def bits_needed(persona):
    return entropy_bits(persona) + 1.0


def test_reconcile_catches_incoherent_screen():
    persona = gen(random.Random(9), "chrome", "windows")
    persona["screenX"] = 3900
    persona["screenY"] = 720
    assert "screen-incoherent" in reconcile(persona)


def test_reconcile_catches_wrong_touch_points():
    persona = gen(random.Random(9), "chrome", "windows")
    persona["maxTouchPoints"] = 5
    persona["touchPoints"] = 5
    assert "touchpoints-mismatch" in reconcile(persona)


def test_reconcile_catches_timezone_mismatch():
    persona = gen(random.Random(9), "chrome", "windows")
    persona["timezone"] = "Asia/Tokyo"
    persona["languagesZ"] = ["en-US", "en"]
    assert "timezone-locale-mismatch" in reconcile(persona)


def test_reconcile_is_defensive_on_partial_input():
    assert reconcile({}) == ["unknown-browser"]
    assert reconcile(None) == ["unknown-browser"]
    assert reconcile({"browser": "chrome"}) == ["unknown-platform"]
    assert is_valid({"browser": "chrome", "platform": "windows"}) is False


def test_safari_scored_zero_before_and_does_not_now():
    persona = gen(random.Random(4), "safari", "mac")
    assert detect_browser(persona["ua"]) == "safari"
    assert detect_platform(persona["ua"]) == "mac"
    assert fingerprint(persona) == 1.0


def test_edge_is_detected_as_edge():
    persona = gen(random.Random(4), "edge", "windows")
    assert detect_browser(persona["ua"]) == "edge"
    assert detect_platform(persona["ua"]) == "windows"


def test_score_rejects_inconsistent_persona():
    persona = gen(random.Random(6), "chrome", "windows")
    persona["ua"] = persona["ua"].replace("Windows NT 10.0", "X11; Linux x86_64")
    ok, details = score(persona)
    assert ok is False
    assert "inconsistent" in details["reason"]


def test_harden_is_deterministic_and_survives_partial_input():
    persona = gen(random.Random(8), "chrome", "windows")
    assert harden(persona) == harden(persona)
    partial = harden({"screenX": 10, "screenY": 20})
    assert partial["webgl"]["vendor"]
    assert partial["canvasSeed"] != partial["audioSeed"]


def test_persona_seed_ignores_name_and_seed_field():
    persona = gen(random.Random(11), "chrome", "windows")
    other = dict(persona, name="different", seed=1234)
    assert persona_seed(persona) == persona_seed(other)


def test_mean_distance_shows_real_variety():
    distance = mean_distance(n=32, browser="chrome", platform="windows")
    assert 0.4 <= distance <= 1.0


def test_profile_roundtrip():
    persona = gen(random.Random(12), "chrome", "windows")
    profile = Profile.from_dict(persona)
    assert profile.browser == persona["browser"]
    assert profile.to_dict()["screenX"] == persona["screenX"]
    assert is_valid(profile)


def test_make_profile_does_not_duplicate(tmp_path, monkeypatch):
    from models import store

    store.close()
    monkeypatch.setenv("FPSPOOF_HOME", str(tmp_path / "home"))
    try:
        ok, persona = make_profile("chrome", "windows", seed=111)
        assert ok is True
        assert persona["_score"] == 1.0
        first = store.count()
        make_profile("chrome", "windows", seed=111)
        assert store.count() == first
    finally:
        store.close()


def test_probe_profile_reports_real_numbers():
    fp, bits = probe_profile("chrome", "windows")
    assert fp == 1.0
    assert bits > 0


def test_generate_respects_requested_platform():
    persona = generate("edge", "mac")
    assert persona["platform"] == "mac"
    assert persona["platformKey"] == "MacIntel"
    assert "Intel Mac OS X" in persona["ua"]
