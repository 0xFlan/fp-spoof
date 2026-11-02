"""Author in the real popup, then prove Chrome reports it and routes as chosen.

The popup is loaded as an extension page in a real browser and driven through
its own handlers: the city select, the route select, and the Save button. The
resulting persona is exported from the page's own ``schema.js`` (the same module
the UI and worker use), handed to the launcher exactly as ``fps launch`` would,
and the live browser is compared against both the resolved persona and the
strings the popup actually rendered.

Routing is proved with local listeners:

* proxy mode — Chrome must send an absolute-form request to the proxy listener,
  including the persona's User-Agent;
* SOCKS5 mode — Chrome must complete a SOCKS5 CONNECT through a local SOCKS5
  listener, and the origin must receive the persona's User-Agent;
* direct mode — the origin listener must see the request and the proxy must see
  nothing.

System/VPN is OS-level by design. It cannot be started, stopped or verified from
an extension or from the launcher, so the script asserts the product says so
rather than pretending the choice changed the tunnel.
"""

from __future__ import annotations

import json
import random
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from fpr.fingerprint import gen
from launcher.launch import PROBE_JS, chrome_path, launch, proxy_args, verify_persona
try:
    from tools.socks5_listener import Socks5Listener
except ModuleNotFoundError:  # run directly as tools/gui_roundtrip.py
    from socks5_listener import Socks5Listener

ROOT = Path(__file__).resolve().parent.parent
EXTENSION = ROOT / "extension"
README = ROOT / "README.md"
UNROUTABLE = "gui.fpspoof.test"
PAGE = (
    "<!doctype html><html><head><meta charset='utf-8'>"
    "<script>window.__PROXY_SERVED__ = 'yes';</script></head>"
    "<body>gui round-trip probe</body></html>"
)


class Listener:
    """Local HTTP listener that records every request it is asked to serve."""

    def __init__(self) -> None:
        self.requests = []
        outer = self

        class Handler(BaseHTTPRequestHandler):
            protocol_version = "HTTP/1.1"

            def log_message(self, *args):  # noqa: D401 - silence
                return

            def handle_one_request(self):
                try:
                    super().handle_one_request()
                except (BrokenPipeError, ConnectionResetError):
                    self.close_connection = True

            def do_GET(self):  # noqa: N802 - BaseHTTPRequestHandler API
                outer.requests.append({
                    "line": self.requestline,
                    "host": self.headers.get("Host"),
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


class Popup:
    """The extension popup rendered as a tab and driven through its handlers."""

    def __init__(self, session) -> None:
        self.session = session
        target = session.cdp.call("Target.createTarget", {"url": "about:blank"})
        self.target_id = target["targetId"]
        self.sid = session.cdp.call(
            "Target.attachToTarget", {"targetId": self.target_id, "flatten": True}
        )["sessionId"]
        session.cdp.call("Page.enable", {}, session_id=self.sid)
        session.cdp.call("Runtime.enable", {}, session_id=self.sid)
        url = "chrome-extension://%s/src/popup.html" % session.extension_id
        session.cdp.call("Page.navigate", {"url": url}, session_id=self.sid)
        if not wait_until(lambda: self.eval("document.readyState") == "complete", 20):
            raise RuntimeError("popup page never loaded")
        if not wait_until(
            lambda: self.eval(
                "(() => { const n = document.querySelector('#quick-city');"
                " return !!n && n.options.length > 1; })()"
            ),
            15,
        ):
            raise RuntimeError("popup never populated its city picker")

    def eval(self, expression):
        return self.session.cdp.evaluate(expression, session_id=self.sid, await_promise=True)

    def choose(self, route: str, port: int | None = None, scheme: str = "http") -> None:
        script = """(() => {
          const city = document.querySelector('#quick-city');
          city.value = 'Asia/Tokyo';
          const route = document.querySelector('#quick-route');
          route.value = %s;
          route.dispatchEvent(new Event('change', { bubbles: true }));
          document.querySelector('#quick-scheme').value = %s;
          document.querySelector('#quick-host').value = '127.0.0.1';
          document.querySelector('#quick-port').value = %s;
          document.querySelector('#quick-save').click();
          return true;
        })()""" % (json.dumps(route), json.dumps(scheme), json.dumps(str(port or "")))
        self.eval(script)

    def ip_text(self) -> str:
        return self.eval("document.querySelector('#ip-note').textContent")

    def capture(self) -> dict:
        return self.eval("""(async () => {
          const schema = await import(chrome.runtime.getURL('src/schema.js'));
          const stored = await chrome.storage.local.get(null);
          const mirror = await (await fetch(chrome.runtime.getURL('personas.json'))).json();
          const name = stored.active || mirror.default;
          const persona = schema.mergePersona(
            mirror.personas[name], (stored.overrides || {})[name]);
          const rows = {};
          document.querySelectorAll('#summary div').forEach((row) => {
            rows[row.querySelector('span').textContent] = row.querySelector('b').textContent;
          });
          const city = document.querySelector('#quick-city').selectedOptions[0];
          return {
            name: name,
            persona: persona,
            rows: rows,
            ip: document.querySelector('#ip-note').textContent,
            note: document.querySelector('#quick-note').textContent,
            city: city ? city.textContent : ''
          };
        })()""")


def wait_until(predicate, timeout: float = 20.0, interval: float = 0.2) -> bool:
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            if predicate():
                return True
        except Exception:
            pass
        time.sleep(interval)
    return False


def displayed_rows_match(capture: dict) -> list[str]:
    """Check the strings the popup rendered against the persona it resolved."""
    p = capture["persona"]
    rows = capture["rows"]
    problems = []
    screen = "%d\u00d7%d @%gx" % (p["screenX"], p["screenY"], p["pixelRatio"])
    if rows.get("screen") != screen:
        problems.append("screen row %r != %r" % (rows.get("screen"), screen))
    memory = "n/a" if p.get("deviceMemory") is None else "%s GB" % p["deviceMemory"]
    cores = "%s / %s" % (p["hardwareConcurrency"], memory)
    if rows.get("cores / mem") != cores:
        problems.append("cores row %r != %r" % (rows.get("cores / mem"), cores))
    locale = rows.get("locale") or ""
    for part in (",".join(p.get("languagesZ") or []), p.get("timezone") or "", "Tokyo"):
        if part not in locale:
            problems.append("locale row %r missing %r" % (locale, part))
    if not rows.get("gpu") or rows["gpu"] not in str(p.get("webglRenderer")):
        problems.append("gpu row %r not in renderer %r" % (rows.get("gpu"), p.get("webglRenderer")))
    if "Tokyo" not in capture.get("city", ""):
        problems.append("city picker did not show Tokyo: %r" % capture.get("city"))
    geo = p.get("geo") or {}
    if abs(float(geo.get("latitude", 0)) - 35.6895) > 0.01:
        problems.append("popup latitude %r is not Tokyo" % geo.get("latitude"))
    if abs(float(geo.get("longitude", 0)) - 139.6917) > 0.01:
        problems.append("popup longitude %r is not Tokyo" % geo.get("longitude"))
    return problems


def main() -> int:
    binary = chrome_path()
    if not binary:
        print("SKIP: no Chromium-family browser installed")
        return 0

    proxy = Listener().__enter__()
    origin = Listener().__enter__()
    socks = Socks5Listener(("127.0.0.1", origin.port)).__enter__()
    author = None
    sessions = []
    ok = True
    try:
        author = launch(gen(random.Random(7), "chrome", "windows"), url="about:blank",
                        headless=True, chrome=binary, extension=str(EXTENSION))
        if not author.extension_id:
            print("FAIL: extension did not mount: %s" % author.extension_error)
            return 1
        popup = Popup(author)
        print("extension id:", author.extension_id)
        print("popup city options:", popup.eval(
            "document.querySelector('#quick-city').options.length"))

        captures = {}

        def settle(route, port, needle, scheme):
            popup.choose(route, port, scheme)
            capture = None

            def saved():
                nonlocal capture
                candidate = popup.capture()
                proxy_value = candidate["persona"].get("proxy") or {}
                matches = proxy_value.get("mode") == route
                if route == "fixed_servers":
                    matches = matches and proxy_value.get("scheme") == scheme
                matches = matches and needle in candidate["ip"].lower()
                if matches:
                    capture = candidate
                return matches

            return capture if wait_until(saved, 15) else None

        routes = (
            ("http", "fixed_servers", proxy.port,
             "via http://127.0.0.1:%d" % proxy.port, "http"),
            ("socks5", "fixed_servers", socks.port,
             "via socks5://127.0.0.1:%d" % socks.port, "socks5"),
            ("direct", "direct", None, "direct \u00b7", "http"),
            ("system", "system", None, "system / vpn", "http"),
        )
        for key, route, port, needle, scheme in routes:
            capture = settle(route, port, needle, scheme)
            if capture is None:
                print("FAIL: popup never settled on %s: %r" % (key, popup.ip_text()))
                return 1
            saved_proxy = capture["persona"].get("proxy") or {}
            if key == "socks5" and saved_proxy.get("username") is not None:
                print("FAIL: SOCKS5 saved credentials Chrome cannot send")
                return 1
            problems = displayed_rows_match(capture)
            if problems:
                print("FAIL: popup display does not match resolved persona:")
                for problem in problems:
                    print("  -", problem)
                return 1
            captures[key] = capture
            print("\n[%s] popup IP row: %s" % (key, capture["ip"]))
            print("[%s] popup displayed: %s" % (key, json.dumps(capture["rows"], ensure_ascii=False)))
            print("[%s] saved persona: tz=%s language=%s geo=%s,%s screen=%sx%s@%s scheme=%s" % (
                key, capture["persona"].get("timezone"),
                (capture["persona"].get("languagesZ") or [None])[0],
                round(capture["persona"]["geo"]["latitude"], 4),
                round(capture["persona"]["geo"]["longitude"], 4),
                capture["persona"]["screenX"], capture["persona"]["screenY"],
                capture["persona"]["pixelRatio"],
                (capture["persona"].get("proxy") or {}).get("scheme")))

        proxy_capture = captures["http"]
        socks_capture = captures["socks5"]
        direct_capture = captures["direct"]
        system_capture = captures["system"]
        persona = proxy_capture["persona"]

        # The repo's own observed-vs-expected comparison, now including the
        # resolved locale and audio noise the new UI can author.
        result = verify_persona(
            persona,
            chrome=binary,
            proxy=persona.get("proxy"),
            other_persona=gen(random.Random(99), "chrome", "windows"),
        )
        observed = result["observed"]
        print("\nlauncher observed values:")
        print(json.dumps({
            "navigator.language(s)": observed.get("languages"),
            "Intl timezone": observed.get("timezone"),
            "Intl resolved locale": observed.get("resolvedLocale"),
            "screen": [observed.get("screenW"), observed.get("screenH"),
                       observed.get("availW"), observed.get("availH")],
            "dpr": observed.get("dpr"),
            "cores": observed.get("hardwareConcurrency"),
            "memory": observed.get("deviceMemory"),
            "webgl vendor": observed.get("glVendor"),
            "webgl renderer": observed.get("glRenderer"),
            "canvas hash": observed.get("canvasHash"),
            "audio hash": observed.get("audioHash"),
            "geolocation": [observed.get("geoLat"), observed.get("geoLon")],
        }, indent=2, ensure_ascii=False))
        failed = [check for check in result["checks"] if not check["ok"]]
        print("observed-vs-expected: %d/%d ok" % (
            len(result["checks"]) - len(failed), len(result["checks"])))
        for check in failed:
            print("  FAIL", check["name"], "expected", check["expected"], "actual", check["actual"])
        ok = ok and result["passed"]
        ok = ok and observed.get("languages") == ",".join(persona["languagesZ"])
        ok = ok and observed.get("resolvedLocale") == persona["languagesZ"][0]
        ok = ok and observed.get("timezone") == persona["timezone"]
        ok = ok and observed.get("audioHash") is not None
        ok = ok and observed.get("canvasHash") is not None

        # Route proof 1: a proxy-only host must arrive at the proxy listener.
        before = len(proxy.requests)
        session = launch(persona, url="http://%s:%d/" % (UNROUTABLE, proxy.port),
                         headless=True, chrome=binary, proxy=persona["proxy"])
        sessions.append(session)
        served = session.evaluate("window.__PROXY_SERVED__ || null")
        via_proxy = session.evaluate(PROBE_JS)
        seen = proxy.requests[before:]
        print("\nproxy route: request lines seen by the proxy listener:")
        for entry in seen:
            print("  ", entry["line"])
        routed = [entry for entry in seen if UNROUTABLE in (entry["host"] or "")]
        proxy_ok = bool(routed) and served == "yes"
        proxy_ok = proxy_ok and any(entry["line"].startswith("GET http://") for entry in routed)
        proxy_ok = proxy_ok and any(entry["ua"] == persona["ua"] for entry in routed)
        proxy_ok = proxy_ok and via_proxy.get("ua") == persona["ua"]
        ok = ok and proxy_ok
        print("proxy route honoured:", proxy_ok)

        # Route proof 2: direct must reach the origin and never the proxy.
        before = len(proxy.requests)
        direct_persona = direct_capture["persona"]
        session = launch(direct_persona, url="http://127.0.0.1:%d/" % origin.port,
                         headless=True, chrome=binary, proxy=direct_persona.get("proxy"))
        sessions.append(session)
        direct_served = session.evaluate("window.__PROXY_SERVED__ || null")
        via_direct = session.evaluate(PROBE_JS)
        direct_ok = direct_served == "yes" and origin.requests
        direct_ok = direct_ok and proxy.requests[before:] == []
        direct_ok = direct_ok and via_direct.get("ua") == direct_persona["ua"]
        ok = ok and direct_ok
        print("direct route honoured:", direct_ok,
              "(origin requests: %d, proxy requests: %d)" % (
                  len(origin.requests), len(proxy.requests[before:])))

        # SOCKS5 route: a real local listener, the origin, and the persona UA.
        before_socks = len(socks.connections)
        before_origin = len(origin.requests)
        socks_persona = socks_capture["persona"]
        session = launch(socks_persona,
                         url="http://socks.fpspoof.test:%d/" % origin.port,
                         headless=True, chrome=binary,
                         proxy=socks_persona.get("proxy"))
        sessions.append(session)
        socks_served = session.evaluate("window.__PROXY_SERVED__ || null")
        via_socks = session.evaluate(PROBE_JS)
        socks_seen = socks.connections[before_socks:]
        origin_seen = origin.requests[before_origin:]
        socks_ok = socks_served == "yes" and bool(socks_seen)
        socks_ok = socks_ok and any(
            entry["host"] == "socks.fpspoof.test" and entry["port"] == origin.port
            for entry in socks_seen)
        socks_ok = socks_ok and any(
            entry["ua"] == socks_persona["ua"] for entry in origin_seen)
        socks_ok = socks_ok and via_socks.get("ua") == socks_persona["ua"]
        ok = ok and socks_ok
        print("\nSOCKS5 route honoured:", socks_ok,
              "(handshakes: %d, origin requests: %d)" % (len(socks_seen), len(origin_seen)))
        for entry in socks_seen:
            print("  SOCKS5 CONNECT %s:%s" % (entry["host"], entry["port"]))

        # Restore the SOCKS5 choice after leaving it: no stale scheme or credentials.
        popup.choose("direct")
        left = wait_until(lambda: "direct \u00b7" in popup.ip_text().lower(), 10)
        restored = settle("fixed_servers", socks.port,
                          "via socks5://127.0.0.1:%d" % socks.port, "socks5")
        restored_proxy = (restored or {}).get("persona", {}).get("proxy") or {}
        restore_ok = bool(left) and bool(restored)
        restore_ok = restore_ok and restored_proxy.get("scheme") == "socks5"
        restore_ok = restore_ok and str(restored_proxy.get("host")) == "127.0.0.1"
        restore_ok = restore_ok and int(restored_proxy.get("port") or 0) == socks.port
        restore_ok = restore_ok and restored_proxy.get("username") is None
        ok = ok and restore_ok
        print("SOCKS5 selection restored without stale credentials:", restore_ok)

        # System/VPN is OS-owned: assert the product states that, and that the
        # launcher adds no routing flag of its own.
        system_note = system_capture["ip"].lower()
        readme = README.read_text(encoding="utf-8").lower()
        system_ok = ("system / vpn" in system_note and "os route" in system_note)
        system_ok = system_ok and proxy_args(system_capture["persona"].get("proxy")) == []
        system_ok = system_ok and "os-owned" in readme
        system_ok = system_ok and "start, stop, or verify" in readme
        ok = ok and system_ok
        print("system/VPN route stated as OS-owned:", system_ok)
        print("system route launcher flags:", proxy_args(system_capture["persona"].get("proxy")))

        print("\nRESULT:", "PASS" if ok else "FAIL")
        return 0 if ok else 1
    finally:
        for session in sessions:
            session.close()
        if author is not None:
            author.close()
        proxy.__exit__()
        origin.__exit__()
        socks.__exit__()


if __name__ == "__main__":
    sys.exit(main())
