"""Deterministic-core tests. No browser required."""
import pytest

from fpr import entropy
from fpr.stability import digest
from fix.reconcile import reconcile
from synth import tables
from synth.mint import MintError, mint
from verify.fingerprintjs_vX import consistency

ALL_COMBOS = [
    (platform, browser)
    for platform, browsers in sorted(tables.ALLOWED.items())
    for browser in browsers
]

FORBIDDEN_IN_GENERATOR = ("verify.truth", "TRUTH_PATH")

# What navigator.platform actually returns, per engine. Anything outside this
# set is a value no browser emits, so the renderer would leak immediately.
REAL_NAVIGATOR_PLATFORM = {"Win32", "MacIntel", "Linux x86_64", "iPhone"}


def test_mint_is_deterministic():
    assert mint(111) == mint(111)


def test_mint_varies_by_seed():
    assert digest(mint(111)) != digest(mint(112))


def test_digest_repeats_for_same_seed():
    assert digest(mint(111)) == digest(mint(111))


def test_every_combo_mints_and_reconciles():
    for platform, browser in ALL_COMBOS:
        profile = mint(7, browser, platform)
        assert reconcile(profile) == [], (platform, browser, reconcile(profile))


def test_platform_key_uses_the_string_a_browser_actually_reports():
    assert set(tables.PLATFORM_KEY.values()) <= REAL_NAVIGATOR_PLATFORM


@pytest.mark.parametrize("platform,browser", ALL_COMBOS)
def test_consistency_is_maximal(platform, browser):
    assert consistency(mint(7, browser, platform)) == 1.0


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
        "pixelRatio": {"n": 50, "bits": 1.0},
        "zone": {"n": 50, "bits": 0.995},
    }
    assert entropy.passes(report) == (True, [])


def test_high_entropy_fields_are_still_gated():
    ok, failures = entropy.passes({"deviceMemory": {"n": 50, "bits": 0.5}})
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
