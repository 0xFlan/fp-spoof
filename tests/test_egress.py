"""Egress observed, not argued.

A local listener acts as an HTTP proxy. A persona whose ``proxy`` points at it
is launched in real Chrome, through the same ``launch()`` that backs
``fps launch``, with the unpacked extension mounted. The listener records the
browser's request: if Chrome bypassed the proxy the request would never arrive
and the test fails loudly (the target host does not resolve, so a bypass cannot
quietly succeed).

The negative case is the same launch with no proxy: the page loads from a second
listener, and the proxy listener must stay empty.
"""

import random
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest

from fpr.fingerprint import gen
from launcher.launch import chrome_path, launch

REPO = Path(__file__).resolve().parents[1]
EXTENSION = REPO / "extension"

# A host nothing can resolve: only a proxy can route it. That is what makes a
# bypass fail instead of silently falling back to a direct connection.
UNROUTABLE = "probe.fpspoof.test"

PAGE = (
    "<!doctype html><html><head><meta charset='utf-8'><title>proxy probe</title>"
    "<script>window.__PROXY_SERVED__ = 'yes';</script></head>"
    "<body>served</body></html>"
)


def _apply_network_until(session, persona, webrtc, mode, attempts=6):
    """Apply through the extension and read back until the policy settles.

    chrome.privacy writes propagate asynchronously; a single immediate read can
    see the previous value and make an otherwise green run fail. This waits for
    the observed state instead of assuming the first read is final.
    """
    result = None
    for _ in range(attempts):
        result = session.apply_extension_network(persona)
        observed = (result or {}).get("observed") or {}
        if observed.get("webrtc") == webrtc and (observed.get("proxy") or {}).get("mode") == mode:
            return result
        time.sleep(0.4)
    return result


class _Listener:
    """Tiny HTTP listener that records every request line it is given.

    Used twice: once as the proxy (Chrome sends absolute-form requests) and once
    as a plain origin server for the no-proxy case, so the two roles cannot be
    confused.
    """

    def __init__(self) -> None:
        self.requests = []
        outer = self

        class Handler(BaseHTTPRequestHandler):
            protocol_version = "HTTP/1.1"

            def log_message(self, *args):  # noqa: D401 - silence
                return

            def do_GET(self):  # noqa: N802 - BaseHTTPRequestHandler API
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
        self._thread = threading.Thread(target=self._httpd.serve_forever, daemon=True)

    def __enter__(self):
        self._thread.start()
        return self

    def __exit__(self, *exc):
        self._httpd.shutdown()
        self._httpd.server_close()


@pytest.fixture()
def proxy() -> _Listener:
    with _Listener() as listener:
        yield listener


@pytest.fixture()
def origin() -> _Listener:
    with _Listener() as listener:
        yield listener


@pytest.mark.skipif(chrome_path() is None, reason="no Chromium-family browser installed")
def test_a_persona_proxy_is_the_route_chrome_actually_takes(proxy):
    persona = gen(random.Random(31), "chrome", "windows")
    persona["proxy"] = {
        "scheme": "http",
        "host": "127.0.0.1",
        "port": proxy.port,
        "bypass": [],
    }
    before = len(proxy.requests)
    session = launch(persona, url="about:blank", headless=True,
                     extension=str(EXTENSION), proxy=persona["proxy"])
    try:
        session.goto("http://%s:%d/" % (UNROUTABLE, proxy.port))
        served = session.evaluate("window.__PROXY_SERVED__ || null")
        network = _apply_network_until(session, persona, "disable_non_proxied_udp", "fixed_servers")
    finally:
        session.close()
        time.sleep(0.5)

    seen = proxy.requests[before:]
    assert seen, "Chrome never reached the proxy — egress bypassed it"
    assert any(UNROUTABLE in (entry["host"] or "") for entry in seen), seen
    assert any(entry["line"].startswith("GET http://") for entry in seen), \
        "an HTTP proxy receives absolute-form requests: %s" % seen
    assert served == "yes", "the page did not come back from the proxy"

    assert network["observed"]["proxy"]["mode"] == "fixed_servers", network
    assert network["observed"]["webrtc"] == "disable_non_proxied_udp", network
    assert network["applied"]["cleared"] is False, network


@pytest.mark.skipif(chrome_path() is None, reason="no Chromium-family browser installed")
def test_a_persona_without_a_proxy_never_touches_the_proxy(proxy, origin):
    persona = gen(random.Random(32), "chrome", "windows")
    persona["proxy"] = None
    before = len(proxy.requests)
    session = launch(persona, url="about:blank", headless=True,
                     extension=str(EXTENSION), proxy=None)
    try:
        session.goto("http://127.0.0.1:%d/" % origin.port)
        served = session.evaluate("window.__PROXY_SERVED__ || null")
        network = _apply_network_until(session, persona, "default", None)
    finally:
        session.close()
        time.sleep(0.5)

    assert served == "yes", "the direct page did not load"
    assert proxy.requests[before:] == [], "a persona with no proxy used the proxy"
    assert origin.requests, "the origin listener never saw the direct request"
    assert network["observed"]["proxy"]["mode"] != "fixed_servers", network
    assert network["observed"]["webrtc"] == "default", network
