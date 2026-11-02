"""Provider URLs, routing modes and credentials for the egress proxy."""

import pytest

from fpr import net
from launcher.launch import proxy_args
from models import store


@pytest.fixture
def isolated(tmp_path, monkeypatch):
    monkeypatch.setenv("FPSPOOF_HOME", str(tmp_path))
    monkeypatch.setenv("FPSPOOF_DB", str(tmp_path / "proxy.db"))
    monkeypatch.setenv("FPSPOOF_EXTENSION", str(tmp_path / "ext"))
    yield tmp_path
    store.close()


def test_provider_url_normalises_into_a_payload():
    parsed = net.parse("socks5://alice:s3cret@10.0.0.5:1080")
    assert parsed["mode"] == "fixed_servers"
    assert parsed["scheme"] == "socks5"
    assert parsed["host"] == "10.0.0.5"
    assert parsed["port"] == 1080
    assert parsed["username"] == "alice"
    assert parsed["password"] == "s3cret"
    assert parsed["bypass"] == ["localhost", "127.0.0.1"]


def test_plain_host_port_and_ipv6_are_understood():
    plain = net.parse("10.0.0.5:3128")
    assert (plain["scheme"], plain["host"], plain["port"]) == ("http", "10.0.0.5", 3128)
    assert net.parse("http://[::1]:8080")["host"] == "::1"


def test_percent_encoded_credentials_are_decoded():
    parsed = net.parse("http://user:p%40ss@127.0.0.1:8080")
    assert parsed["username"] == "user"
    assert parsed["password"] == "p@ss"


@pytest.mark.parametrize(
    "bad",
    ["gopher://host:1", "host", "host:0", "host:70000", "http://:8080"],
)
def test_impossible_proxies_are_refused(bad):
    with pytest.raises(net.ProxyError):
        net.parse(bad)


def test_modes_are_first_class_not_a_hidden_default():
    assert net.parse({"mode": "system"}) == {"mode": "system"}
    assert net.parse({"mode": "direct"}) == {"mode": "direct"}
    assert net.is_proxy({"mode": "direct"}) is False
    assert net.is_proxy({"scheme": "http", "host": "h", "port": 1}) is True
    assert "VPN" in net.describe(None)
    assert "direct" in net.describe({"mode": "direct"})
    assert net.problems({"mode": "tunnel"}) == ["proxy-mode"]


def test_launcher_flags_follow_the_mode():
    assert proxy_args({"mode": "system"}) == []
    assert proxy_args({"mode": "direct"}) == ["--no-proxy-server"]
    flags = proxy_args({"scheme": "socks5", "host": "10.0.0.5", "port": 1080})
    assert "--proxy-server=socks5://10.0.0.5:1080" in flags
    assert "--force-webrtc-ip-handling-policy=disable_non_proxied_udp" in flags
    assert proxy_args({"scheme": "bogus"}) == []


def test_provider_url_and_modes_persist_through_the_cli(isolated):
    from api.cli import main

    assert main(["roll", "-b", "chrome", "-p", "mac", "--seed", "2"]) == 0
    name = store.list_profiles()[0]["name"]

    assert main(["proxy", name, "--url", "socks5://alice:s3cret@10.0.0.5:1080"]) == 0
    proxy = store.get(name)["persona"]["proxy"]
    assert (proxy["host"], proxy["port"], proxy["username"]) == ("10.0.0.5", 1080, "alice")
    assert proxy["password"] == "s3cret"

    assert main(["proxy", name, "--direct"]) == 0
    assert store.get(name)["persona"]["proxy"] == {"mode": "direct"}

    assert main(["proxy", name, "--system"]) == 0
    assert store.get(name)["persona"]["proxy"] == {"mode": "system"}

    assert main(["proxy", name, "--clear"]) == 0
    assert store.get(name)["persona"]["proxy"] is None


def test_an_invalid_provider_url_is_refused_without_writing(isolated):
    from api.cli import main

    assert main(["roll", "-b", "chrome", "-p", "mac", "--seed", "3"]) == 0
    name = store.list_profiles()[0]["name"]
    assert main(["proxy", name, "--url", "gopher://host:1"]) == 1
    assert store.get(name)["persona"]["proxy"] is None
