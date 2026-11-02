"""Tunnel detection and observed egress, executed without touching the network."""

import json
import os
import stat
from pathlib import Path

import pytest

from fpr import egress, vpn

PROTON_DISCONNECTED = "Status: Disconnected\n[!] Kill Switch is currently active.\n"
NORD_CONNECTED = "Status: Connected\nHostname: us8585.nordvpn.com\nCountry: United States\n"
MULLVAD_JSON = '{"state": "connected", "details": {"location": {"city": "Gothenburg"}}}'
TAILSCALE_RUNNING = '{"BackendState": "Running", "ExitNodeStatus": {"ID": "n1"}}'
TAILSCALE_MESH = '{"BackendState": "Running", "ExitNodeStatus": null}'


def _bin(tmp_path, name, body):
    directory = tmp_path / "bin"
    directory.mkdir(exist_ok=True)
    path = directory / name
    path.write_text("#!/bin/sh\n" + body + "\n")
    path.chmod(path.stat().st_mode | stat.S_IEXEC)
    return directory


@pytest.fixture
def fake_clients(tmp_path, monkeypatch):
    _bin(tmp_path, "mullvad", "echo '%s'" % MULLVAD_JSON)
    _bin(tmp_path, "nordvpn", "echo 'Status: Connected'")
    _bin(tmp_path, "protonvpn", "echo 'Status: Disconnected'")
    _bin(tmp_path, "tailscale", "echo '%s'" % TAILSCALE_RUNNING)
    _bin(tmp_path, "wg", "echo 'utun3'")
    monkeypatch.setenv("PATH", str(tmp_path / "bin") + os.pathsep + os.environ.get("PATH", ""))
    return tmp_path


def test_clients_report_their_own_state(fake_clients):
    states = {entry["id"]: entry["state"] for entry in vpn.detect()}
    assert states["mullvad"] == "connected"      # JSON, not the prose line
    assert states["nordvpn"] == "connected"      # anchored "Status: Connected"
    assert states["protonvpn"] == "disconnected"
    assert states["tailscale"] == "connected"    # Running + exit node
    assert states["wg"] == "connected"


def test_a_running_tailscale_without_an_exit_node_is_not_a_full_tunnel():
    assert vpn.parse_state("tailscale", TAILSCALE_MESH) == "mesh"
    assert vpn.parse_state("tailscale", '{"BackendState": "Stopped"}') == "disconnected"


def test_mullvad_prose_is_a_fallback_not_the_contract():
    assert vpn.parse_state("mullvad", "Connected\n    Relay: se-got-wg-001") == "connected"
    assert vpn.parse_state("mullvad", "Disconnected") == "disconnected"


def test_summary_counts_only_real_tunnels_and_mirrors(tmp_path):
    payload = {
        "tunnels": [
            {"id": "a", "label": "A", "installed": True, "state": "connected", "detail": ""},
            {"id": "b", "label": "B", "installed": True, "state": "mesh", "detail": ""},
        ],
        "interfaces": [],
        "active": True,
        "connected": ["A"],
    }
    target = tmp_path / "data" / "vpn.json"
    vpn.write_mirror(payload, target)
    assert json.loads(target.read_text())["connected"] == ["A"]


def test_egress_distance_flags_a_persona_that_does_not_match():
    payload = {"ip": "203.0.113.9", "city": "Sydney", "country": "AU",
               "org": "AS1221 Telstra", "loc": "-33.87,151.21"}
    result = egress.compare(payload, {"geo": {"city": "Berlin", "timezone": "Europe/Berlin",
                                              "lat": 52.52, "lon": 13.40}})
    assert result["observed"]["ip"] == "203.0.113.9"
    assert result["distance_km"] > 10000
    assert any("not the persona's city" in note for note in result["notes"])


def test_egress_without_a_proxy_says_the_ip_is_real():
    payload = {"ip": "198.51.100.4", "city": "Paris", "country": "FR"}
    result = egress.compare(payload, {"geo": {"city": "Paris"}})
    assert result["distance_km"] is None
    assert any("the observed IP is the real one" in note for note in result["notes"])


def test_cli_egress_reports_and_can_emit_json(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("FPSPOOF_HOME", str(tmp_path))
    monkeypatch.setenv("FPSPOOF_DB", str(tmp_path / "egress.db"))
    monkeypatch.setenv("FPSPOOF_EXTENSION", str(tmp_path / "ext"))
    from api.cli import main
    from models import store

    assert main(["roll", "-b", "chrome", "-p", "mac", "--seed", "7"]) == 0
    name = store.list_profiles()[0]["name"]
    monkeypatch.setattr(egress, "fetch", lambda url=None, timeout=None: {
        "ip": "203.0.113.9", "city": "Sydney", "country": "AU",
        "org": "AS1221 Telstra", "loc": "-33.87,151.21"})
    capsys.readouterr()
    assert main(["egress", name, "--json"]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["observed"]["ip"] == "203.0.113.9"
    assert main(["egress", name]) == 0
    assert "egress" in capsys.readouterr().out
    store.close()


def test_cli_vpn_emits_structured_output(capsys):
    from api.cli import main

    assert main(["vpn", "--json"]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert isinstance(payload["tunnels"], list)
    assert "interfaces" in payload
