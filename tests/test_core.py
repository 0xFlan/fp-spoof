"""Deterministic-core tests. No browser required."""

import pytest

from fpr import entropy
from fpr.stability import digest
from fix.reconcile import reconcile
from synth import tables
from synth.mint import MintError, mint
from verify import truth
from verify.fingerprintjs_vX import consistency

ALL_COMBOS = [
    (platform, browser)
    for platform, browsers in sorted(tables.ALLOWED.items())
    for browser in browsers
]

FORBIDDEN_IN_GENERATOR = ("verify.truth", "TRUTH_PATH")

# What navigator.platform actually returns, per engine. Anything outside this
# set is a value no browser emits, so the renderer would leak immediately.
REAL_NAVIGATOR_PLATFORM = {"Win32", "MacIntel", "Linux x86_64"}

# Chrome bucketed it to a power of two and clamps at 8 GiB, so nothing above 8
# can appear in a real browser.
CHROME_DEVICE_MEMORY = {0.25, 0.5, 1, 2, 4, 8}


def _record(profile) -> dict:
    return profile.to_dict()


def test_mint_is_deterministic():
    assert mint(111) == mint(111)


def test_mint_varies_by_seed():
    assert digest(mint(111)) != digest(mint(112))


def test_digest_repeats_for_same_seed():
    assert digest(mint(111)) == digest(mint(111))


def test_profile_name_identifies_the_device():
    assert mint(111, "edge", "mac").name == "profile-edge-mac-111"
    assert mint(111).name != mint(112).name


def test_every_combo_mints_and_reconciles():
    for platform, browser in ALL_COMBOS:
        profile = mint(7, browser, platform)
        assert reconcile(profile) == [], (platform, browser, reconcile(profile))


def test_platform_key_uses_the_string_a_browser_actually_reports():
    assert set(tables.PLATFORM_KEY.values()) <= REAL_NAVIGATOR_PLATFORM


def test_generator_emits_only_device_memory_chrome_can_report():
    for platform, values in tables.MEMORY.items():
        assert set(values) <= CHROME_DEVICE_MEMORY, platform


def test_truth_holds_only_device_memory_chrome_can_report():
    for platform in truth.platforms():
        distribution = truth.distributions(platform).get("deviceMemory", {})
        assert set(distribution) <= CHROME_DEVICE_MEMORY, platform


def test_truth_describes_every_platform_the_generator_offers():
    assert set(truth.platforms()) == set(tables.ALLOWED)


@pytest.mark.parametrize("platform,browser", ALL_COMBOS)
def test_consistency_is_maximal(platform, browser):
    assert consistency(mint(7, browser, platform)) == 1.0


@pytest.mark.parametrize("platform", sorted(tables.ALLOWED))
def test_a_population_passes_the_audit_gates(platform):
    browsers = tables.ALLOWED[platform]
    profiles = [
        mint(seed, browsers[seed % len(browsers)], platform) for seed in range(120)
    ]
    report = entropy.population_report(profiles, truth.distributions(platform))
    ok, failures = entropy.passes(report)
    assert ok, failures
    assert [profile.name for profile in profiles if reconcile(profile)] == []


def test_every_zone_is_reachable():
    zones = {mint(seed).zone for seed in range(200)}
    assert zones == set(tables.ZONE_OFFSETS)


def test_screen_and_dpr_are_drawn_together():
    for seed in range(120):
        profile = mint(seed)
        if profile.pixelRatio >= 2:
            assert profile.screenX >= 1440, profile


def test_cores_and_memory_are_drawn_together():
    for seed in range(120):
        profile = mint(seed)
        if profile.hardwareConcurrency >= 12:
            assert profile.deviceMemory >= 8, profile


def test_language_and_zone_are_drawn_together():
    for seed in range(120):
        profile = mint(seed)
        assert profile.zone in tables.LANGUAGE_ZONES[profile.languagesZ[0]]


def test_every_language_has_zones_and_every_zone_a_language():
    assert {language[0] for language in tables.LANGUAGES} == set(tables.LANGUAGE_ZONES)
    for zones in tables.LANGUAGE_ZONES.values():
        assert zones
        assert set(zones) <= set(tables.ZONE_OFFSETS)


def test_reconcile_catches_planted_contradictions():
    base = _record(mint(7, "chrome", "windows"))

    low_res_retina = dict(base, pixelRatio=2.0, screenX=1280, screenY=720)
    assert "screen-vs-dpr" in reconcile(low_res_retina)

    thin_memory = dict(base, hardwareConcurrency=16, deviceMemory=4)
    assert "cores-vs-memory" in reconcile(thin_memory)

    displaced = dict(base, languagesZ=("en-US", "en"), zone=9)
    assert "zone-vs-language:en-US@9" in reconcile(displaced)

    no_plugins = dict(base, plugins=())
    assert "plugin-set" in reconcile(no_plugins)


def test_reconcile_rejects_without_raising():
    assert reconcile({"platform": "windows", "browser": "safari"})


def test_reconcile_handles_empty_record():
    assert reconcile({}) == ["unknown-platform:None"]


def test_unknown_browser_is_rejected():
    with pytest.raises(MintError):
        mint(1, "firefox", "windows")


def test_unknown_platform_is_rejected():
    with pytest.raises(MintError):
        mint(1, "chrome", "beos")


def test_safari_is_no_longer_expressible():
    assert "safari" not in {b for browsers in tables.ALLOWED.values() for b in browsers}
    assert not [key for key in tables.UA_TEMPLATES if key[0] == "safari"]
    with pytest.raises(MintError):
        mint(1, "safari", "mac")


def test_ios_is_no_longer_expressible():
    assert "ios" not in tables.ALLOWED
    with pytest.raises(MintError):
        mint(1, "chrome", "ios")


def test_plugin_set_depends_only_on_the_browser():
    for platform, browser in ALL_COMBOS:
        expected = sorted(tables.PLUGINS_BY_BROWSER[browser])
        for seed in range(12):
            assert sorted(mint(seed, browser, platform).plugins) == expected
    assert set(tables.PLUGINS_BY_BROWSER["chrome"]) != set(
        tables.PLUGINS_BY_BROWSER["edge"]
    )


def test_a_capability_gap_rejects_a_claimed_value(monkeypatch):
    record = _record(mint(7, "chrome", "windows"))
    monkeypatch.setitem(tables.BROWSER_CAPS["chrome"], "deviceMemory", False)
    assert "deviceMemory-unsupported" in reconcile(record)


def test_generator_never_reads_truth():
    from pathlib import Path

    root = Path(__file__).resolve().parents[1]
    for name in ("synth/tables.py", "synth/mint.py", "fix/harden.py"):
        text = (root / name).read_text(encoding="utf-8")
        for token in FORBIDDEN_IN_GENERATOR:
            assert token not in text, f"{name} references {token}"


def test_field_entropy_of_a_constant_is_zero():
    assert entropy.field_bits([7, 7, 7]) == 0.0


def test_kl_is_zero_for_identical_distribution():
    sample = [8, 16, 8, 16]
    assert entropy.kl_bits(sample, entropy.empirical(sample), alpha=0.0) == pytest.approx(
        0.0, abs=1e-12
    )


def test_support_gaps_flags_values_truth_lacks():
    gaps = entropy.support_gaps([8, 16], {8: 0.5, 32: 0.5})
    assert gaps["missing"] == ["32"]
    assert gaps["unknown"] == ["16"]


def test_population_report_covers_default_fields():
    profiles = [mint(seed) for seed in range(40)]
    report = entropy.population_report(profiles, {"deviceMemory": {8: 0.5, 16: 0.5}})
    assert set(report) == {"deviceMemory", "hardwareConcurrency", "pixelRatio", "zone"}
    assert report["deviceMemory"]["bits"] > 0


def test_low_entropy_fields_are_not_gated_on_bits():
    report = {
        "deviceMemory": {"n": 50, "bits": 1.0},
        "pixelRatio": {"n": 50, "bits": 1.0},
        "zone": {"n": 50, "bits": 0.995},
    }
    assert entropy.passes(report) == (True, [])


def test_high_entropy_fields_are_still_gated():
    ok, failures = entropy.passes({"hardwareConcurrency": {"n": 50, "bits": 0.5}})
    assert not ok
    assert "bits" in failures[0]


def test_support_gaps_still_fail_a_low_entropy_field():
    report = {
        "pixelRatio": {
            "n": 50,
            "bits": 1.0,
            "support": {"unknown": ["3"], "missing": []},
        }
    }
    ok, failures = entropy.passes(report)
    assert not ok
    assert "truth never has" in failures[0]


def test_cli_exposes_the_documented_commands():
    from api.run import build_parser

    parser = build_parser()
    for command in ("mint", "probe", "list", "audit", "live"):
        assert parser.parse_args([command]).command == command


def test_store_upsert_is_idempotent(tmp_path, monkeypatch):
    from models import store

    monkeypatch.setenv("FP_SPOOF_DB", str(tmp_path / "p.db"))
    profile = mint(111)
    store.save(profile, consistency=1.0)
    store.save(profile, consistency=1.0)
    assert len(store.list_profiles()) == 1


def test_store_preserves_hits_on_resave(tmp_path, monkeypatch):
    from models import store

    monkeypatch.setenv("FP_SPOOF_DB", str(tmp_path / "p.db"))
    profile = mint(111)
    store.save(profile, consistency=1.0)
    store.record_hit(profile.name)
    store.save(profile, consistency=1.0)
    assert store.get(profile.name)[7] == 1


def test_list_on_fresh_database(tmp_path, monkeypatch):
    from models import store

    monkeypatch.setenv("FP_SPOOF_DB", str(tmp_path / "fresh.db"))
    assert store.list_profiles() == []


def test_payload_roundtrips(tmp_path, monkeypatch):
    from models import store

    monkeypatch.setenv("FP_SPOOF_DB", str(tmp_path / "p.db"))
    profile = mint(111)
    store.save(profile, consistency=1.0)
    data = store.payload(profile.name)
    assert data["wglRenderer"] == profile.wglRenderer
    assert data["screenX"] == profile.screenX
