"""SOCKS5 is a real route, not just a select option.

A local SOCKS5 listener records the CONNECT request and tunnels to a local
origin. Chrome must reach that origin through the listener, and the origin must
receive the persona's User-Agent. Both the launcher flag and the extension's
``chrome.proxy`` path are exercised.
"""

from __future__ import annotations

import json
import random
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest

from fpr.fingerprint import gen
from launcher.launch import chrome_path, launch
from tools.socks5_listener import Socks5Listener

REPO = Path(__file__).resolve().parents[1]
EXTENSION = REPO / "extension"
HOST = "socks.fpspoof.test"
PAGE = (
    "<!doctype html><html><head><meta charset='utf-8'>"
    "<script>window.__SOCKS_SERVED__ = 'yes';</script></head>"
    "<body>socks probe</body></html>"
)


class Origin:
    def __init__(self) -> None:
        self.requests = []
        outer = self

        class Handler(BaseHTTPRequestHandler):
            protocol_version = "HTTP/1.1"

            def log_message(self, *args):
                return

            def do_GET(self):  # noqa: N802
                outer.requests.append({
                    "line": self.requestline,
                    "host": self.headers.get("Host"),
                    "path": self.path,
                    "ua": self.headers.get("User-Agent"),
                })
                body = PAGE.encode("utf-8")
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Content-Length", str(len(body)))
                self.send_header("Connection", "close")
                self.end_headers()
                self.wfile.write(body)

        self._httpd = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.port = self._httpd.server_address[1]
        threading.Thread(target=self._httpd.serve_forever, daemon=True).start()

    def close(self) -> None:
        self._httpd.shutdown()
        self._httpd.server_close()


def socks_persona(port: int, seed: int = 41) -> dict:
    persona = gen(random.Random(seed), "chrome", "windows")
    persona["proxy"] = {
        "mode": "fixed_servers",
        "scheme": "socks5",
        "host": "127.0.0.1",
        "port": port,
        "bypass": [],
    }
    return persona


def mirrored_socks_persona(port: int) -> dict:
    """Use the extension's baked default so its DNR headers agree with CDP."""
    payload = json.loads((EXTENSION / "personas.json").read_text(encoding="utf-8"))
    persona = json.loads(json.dumps(payload["personas"][payload["default"]]))
    persona["proxy"] = {
        "mode": "fixed_servers",
        "scheme": "socks5",
        "host": "127.0.0.1",
        "port": port,
        "bypass": [],
    }
    return persona


@pytest.mark.skipif(chrome_path() is None, reason="no Chromium-family browser installed")
def test_launcher_sends_traffic_through_a_real_socks5_listener():
    origin = Origin()
    with Socks5Listener(("127.0.0.1", origin.port)) as socks:
        persona = socks_persona(socks.port)
        session = launch(
            persona,
            url="http://%s:%d/" % (HOST, origin.port),
            headless=True,
            proxy=persona["proxy"],
        )
        try:
            served = session.evaluate("window.__SOCKS_SERVED__ || null")
        finally:
            session.close()
        time.sleep(0.4)
    try:
        assert served == "yes", "the page did not come back through SOCKS5"
        page = [entry for entry in origin.requests if entry["path"] == "/"]
        assert page, "the origin never received the page request: %s" % origin.requests
        assert page[0]["ua"] == persona["ua"], page[0]
        assert any(
            entry["host"] == HOST and entry["port"] == origin.port
            for entry in socks.connections
        ), socks.connections
        assert all(entry["command"] == 1 for entry in socks.connections)
    finally:
        origin.close()


@pytest.mark.skipif(chrome_path() is None, reason="no Chromium-family browser installed")
def test_the_extension_applies_a_socks5_route_through_chrome_proxy():
    origin = Origin()
    with Socks5Listener(("127.0.0.1", origin.port)) as socks:
        persona = mirrored_socks_persona(socks.port)
        session = launch(persona, url="about:blank", headless=True,
                         extension=str(EXTENSION))
        try:
            if not session.extension_id:
                pytest.skip("headless Chrome could not mount the extension: %s"
                            % session.extension_error)
            # A normal local page wakes the service worker before the route
            # changes; a fresh worker is not always evaluating yet.
            session.goto("http://127.0.0.1:%d/" % origin.port)
            network = None
            for _ in range(8):
                network = session.apply_extension_network(persona)
                observed = (network or {}).get("observed") or {}
                if ((observed.get("proxy") or {}).get("mode") == "fixed_servers"
                        and observed.get("webrtc") == "disable_non_proxied_udp"):
                    break
                time.sleep(0.4)
            before_origin = len(origin.requests)
            session.goto("http://%s:%d/" % (HOST, origin.port))
            served = session.evaluate("window.__SOCKS_SERVED__ || null")
        finally:
            session.close()
        time.sleep(0.4)
    try:
        observed = network["observed"]["proxy"]
        assert observed["mode"] == "fixed_servers", network
        assert observed["rules"]["singleProxy"]["scheme"] == "socks5", network
        assert served == "yes", "the extension route did not carry the page"
        page = [entry for entry in origin.requests[before_origin:] if entry["path"] == "/"]
        assert page, "the origin never received the page request: %s" % origin.requests[before_origin:]
        assert page[0]["ua"] == persona["ua"], page[0]
        assert any(
            entry["host"] == HOST and entry["port"] == origin.port
            for entry in socks.connections
        ), socks.connections
    finally:
        origin.close()
