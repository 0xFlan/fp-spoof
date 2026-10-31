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
