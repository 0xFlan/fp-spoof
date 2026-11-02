"""Whole-identity rolls: generated together, validated, never a field mix."""

import pytest

from api.cli import main
from fix.reconcile import reconcile
from fpr import geo as geodata
from models import store


@pytest.fixture
def isolated(tmp_path, monkeypatch):
    monkeypatch.setenv("FPSPOOF_HOME", str(tmp_path))
    monkeypatch.setenv("FPSPOOF_DB", str(tmp_path / "roll.db"))
    monkeypatch.setenv("FPSPOOF_EXTENSION", str(tmp_path / "ext"))
    yield tmp_path
    store.close()


def test_roll_generates_one_whole_coherent_identity(isolated):
    assert main(["roll", "-b", "chrome", "-p", "mac", "--seed", "5"]) == 0
    rows = store.list_profiles()
    assert len(rows) == 1
    persona = rows[0]["persona"]
    assert rows[0]["name"].startswith("chrome-mac-")
    assert reconcile(persona) == []
    city = geodata.city(persona["timezone"])
    assert persona["geo"]["latitude"] == pytest.approx(city["latitude"])
    assert persona["geo"]["longitude"] == pytest.approx(city["longitude"])


def test_roll_never_overwrites_an_existing_identity(isolated):
    assert main(["roll", "-b", "chrome", "-p", "linux", "--seed", "11"]) == 0
    assert main(["roll", "-b", "chrome", "-p", "linux", "--seed", "12"]) == 0
    rows = store.list_profiles()
    assert len({row["name"] for row in rows}) == 2
    for row in rows:
        assert reconcile(row["persona"]) == []


def test_roll_carries_location_connection_and_noise_together(isolated):
    """Every part of the identity comes from the same draw, not from a patch."""
    assert main(["roll", "-b", "safari", "-p", "ios", "--seed", "3"]) == 0
    persona = store.list_profiles()[0]["persona"]
    assert persona["timezone"] in geodata.cities()
    assert persona["geo"]["city"] == geodata.city(persona["timezone"])["city"]
    assert persona["canvasSeed"] and persona["audioSeed"]
    assert persona["canvasSeed"] != persona["audioSeed"]
    assert persona["connection"]["effectiveType"] == "4g"
    assert persona["maxTouchPoints"] == 5
