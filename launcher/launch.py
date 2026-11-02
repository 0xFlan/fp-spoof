"""Launch a Chromium-family browser with a persona applied.

Two layers are covered:

* **Network** — ``Emulation.setUserAgentOverride`` with ``userAgentMetadata``
  rewrites the ``User-Agent`` and ``sec-ch-ua*`` headers, plus locale/timezone
  and metrics overrides.  An extension alone cannot do this consistently.
* **JavaScript** — the same ``extension/src/patch.js`` used by the add-on is
  injected with ``Page.addScriptToEvaluateOnNewDocument``, so it runs before
  any page script and the extension and launcher can never drift apart.
"""

from __future__ import annotations

import http.server
import json
import os
import shutil
import subprocess
import tempfile
import threading
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

from fpr import net
from launcher.cdp import CDPError, PipeCDP

ROOT = Path(__file__).resolve().parents[1]
PATCH_JS = ROOT / "extension" / "src" / "patch.js"

CHROME_CANDIDATES = [
    "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
    "/Applications/Chromium.app/Contents/MacOS/Chromium",
    "/Applications/Brave Browser.app/Contents/MacOS/Brave Browser",
    "/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge",
    "/usr/bin/google-chrome",
    "/usr/bin/chromium",
    "/usr/bin/chromium-browser",
]

CH_PLATFORM = {
    "windows": "Windows",
    "mac": "macOS",
    "linux": "Linux",
    "ios": "iOS",
}


class LaunchError(RuntimeError):
    """Raised when a browser cannot be started or driven."""


def chrome_path() -> Optional[str]:
    """Best installed Chromium-family binary, or ``None``."""
    override = os.environ.get("FPSPOOF_CHROME")
    if override:
        return override if Path(override).exists() else None
    for candidate in CHROME_CANDIDATES:
        if Path(candidate).exists():
            return candidate
    for name in ("google-chrome", "chromium", "chromium-browser", "brave-browser", "microsoft-edge"):
        found = shutil.which(name)
        if found:
            return found
    return None


def patch_source(persona: Dict[str, Any]) -> str:
    """Persona prelude + the shared patch script, ready to inject."""
    if not PATCH_JS.exists():
        raise LaunchError("missing injection script: %s" % PATCH_JS)
    payload = json.dumps(persona, default=str, sort_keys=True)
    return "window.__FPS_PERSONA__ = %s;\n%s" % (payload, PATCH_JS.read_text(encoding="utf-8"))


def user_agent_metadata(persona: Dict[str, Any]) -> Dict[str, Any]:
    uad = persona.get("userAgentData") or {}
    version = str(persona.get("version") or "")
    brands = [{"brand": b.get("brand", ""), "version": str(b.get("version", ""))} for b in uad.get("brands") or []]
    return {
        "brands": brands,
        "fullVersionList": [{"brand": b["brand"], "version": version} for b in brands] or [],
        "fullVersion": version,
        "platform": CH_PLATFORM.get(str(persona.get("platform")), "Windows"),
        "platformVersion": str(uad.get("platformVersion") or "10.0.0"),
        "architecture": str(uad.get("architecture") or "x86"),
        "model": "",
        "mobile": bool(uad.get("mobile")),
        "bitness": str(uad.get("bitness") or "64"),
        "wow64": False,
    }


class Session:
    """A running browser with a persona attached."""

    def __init__(
        self,
        process: subprocess.Popen,
        cdp: PipeCDP,
        profile_dir: str,
        session_id: str,
        extension_id: Optional[str] = None,
        extension_error: Optional[str] = None,
    ) -> None:
        self.process = process
        self.cdp = cdp
        self.profile_dir = profile_dir
        self.session_id = session_id
        self.extension_id = extension_id
        self.extension_error = extension_error
        # Result of running the extension's own network module against the real
        # chrome APIs, when one was applied. None means it was not reachable.
        self.extension_network: Optional[Dict[str, Any]] = None

    def extension_target(self, timeout: float = 20.0) -> Optional[str]:
        """Target id of *this* extension's service worker, once it exists.

        Chrome always runs several component extensions whose workers are also
        ``chrome-extension://`` URLs (they expose metricsPrivate, ttsEngine and
        so on). Matching on the scheme alone silently attached to one of those
        and made ``chrome.proxy`` look absent, so the launched extension id is
        required, with the background script path as a fallback.
        """
        marker = ("chrome-extension://%s/" % self.extension_id
                  if self.extension_id else "/src/background.js")
        deadline = time.time() + timeout
        while time.time() < deadline:
            targets = self.cdp.call("Target.getTargets")["targetInfos"]
            worker = next(
                (t for t in targets
                 if t.get("type") == "service_worker"
                 and marker in (t.get("url") or "")),
                None,
            )
            if worker:
                return worker["targetId"]
            time.sleep(0.2)
        return None

    def evaluate_extension(self, expression: str, timeout: float = 20.0) -> Any:
        """Evaluate in the extension service worker, where ``chrome.*`` lives.

        A page's MAIN world cannot call ``chrome.proxy`` at all, so the only way
        to observe what the extension actually applied is to talk to its worker.
        """
        target = self.extension_target(timeout)
        if target is None:
            raise LaunchError("the extension service worker never started")
        attached = self.cdp.call("Target.attachToTarget", {"targetId": target, "flatten": True})
        session_id = attached["sessionId"]
        try:
            self.cdp.call("Runtime.enable", session_id=session_id)
            return self.cdp.evaluate(expression, session_id=session_id,
                                     await_promise=True)
        finally:
            try:
                self.cdp.call("Target.detachFromTarget", {"sessionId": session_id}, timeout=3)
            except CDPError:
                pass

    def apply_extension_network(self, persona: Dict[str, Any], timeout: float = 20.0) -> Dict[str, Any]:
        """Apply the persona's proxy through the extension's own module.

        The module is imported from the mounted extension, so this executes the
        same ``network.js`` the service worker runs — against the real
        ``chrome.proxy`` and ``chrome.privacy`` APIs — and then reads the applied
        values back instead of trusting the write.
        """
        payload = json.dumps({"proxy": net.parse(persona.get("proxy"))})
        expression = (
            "(async () => {"
            "  if (typeof self.__FPS_APPLY_NETWORK__ !== 'function') {"
            "    return { error: 'network hook missing in the worker' };"
            "  }"
            "  return await self.__FPS_APPLY_NETWORK__(chrome, %s);"
            "})()" % payload
        )
        applied = self.evaluate_extension(expression, timeout=timeout)
        observed = self.evaluate_extension(
            "(async () => ({"
            "  proxy: (await chrome.proxy.settings.get({})).value,"
            "  webrtc: (await chrome.privacy.network.webRTCIPHandlingPolicy.get({})).value"
            "}))()",
            timeout=timeout,
        )
        result = {"applied": applied, "observed": observed}
        self.extension_network = result
        return result

    def goto(self, url: str, timeout: float = 30.0) -> None:
        self.cdp.call("Page.navigate", {"url": url}, session_id=self.session_id, timeout=timeout)
        try:
            self.cdp.wait_for("Page.loadEventFired", timeout=timeout)
        except CDPError:
            # A page that never fires load is still inspectable.
            pass

    def reload(self, timeout: float = 30.0) -> None:
        self.cdp.call("Page.reload", {}, session_id=self.session_id, timeout=timeout)
        try:
            self.cdp.wait_for("Page.loadEventFired", timeout=timeout)
        except CDPError:
            pass

    def evaluate(self, expression: str) -> Any:
        return self.cdp.evaluate(expression, session_id=self.session_id, await_promise=True)

    def wait(self) -> int:
        return self.process.wait()

    def close(self) -> None:
        try:
            self.cdp.call("Browser.close", timeout=5)
        except (CDPError, OSError):
            pass
        try:
            self.process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            self.process.kill()
            try:
                self.process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                pass
        self.cdp.close()
        shutil.rmtree(self.profile_dir, ignore_errors=True)


def proxy_args(proxy: Optional[Dict[str, Any]]) -> List[str]:
    """Chrome flags for a persona proxy.

    Pure on purpose: the flag list can be asserted without starting a browser,
    and the command line is the only place the launcher can affect the egress
    address at all.
    """
    try:
        payload = net.parse(proxy)
    except net.ProxyError:
        return []
    if not payload:
        return []
    if payload.get("mode") == "system":
        return []
    if payload.get("mode") == "direct":
        return ["--no-proxy-server"]
    if not payload.get("host") or not payload.get("port"):
        return []
    return [
        "--proxy-server=%s://%s:%s" % (payload["scheme"], payload["host"], payload["port"]),
        "--force-webrtc-ip-handling-policy=disable_non_proxied_udp",
    ]


def launch(
    persona: Dict[str, Any],
    url: str = "about:blank",
    headless: bool = True,
    extension: Optional[str] = None,
    chrome: Optional[str] = None,
    extra_args: Sequence[str] = (),
    proxy: Optional[Dict[str, Any]] = None,
) -> Session:
    """Start a browser and apply ``persona`` to it."""
    binary = chrome or chrome_path()
    if not binary:
        raise LaunchError("no Chrome/Chromium/Brave/Edge binary found; pass --chrome PATH")
    if not Path(binary).exists():
        raise LaunchError("browser binary not found: %s" % binary)

    source = patch_source(persona)
    profile_dir = tempfile.mkdtemp(prefix="fpspoof-profile-")

    # fd 3: browser reads commands, fd 4: browser writes replies.
    cmd_read, cmd_write = os.pipe()
    out_read, out_write = os.pipe()

    def _child_setup() -> None:  # pragma: no cover - runs in the child
        os.dup2(cmd_read, 3)
        os.dup2(out_write, 4)

    args: List[str] = [
        binary,
        "--remote-debugging-pipe",
        "--user-data-dir=%s" % profile_dir,
        "--no-first-run",
        "--no-default-browser-check",
        "--disable-background-networking",
        "--disable-component-update",
        "--disable-sync",
        "--disable-default-apps",
        "--disable-client-side-phishing-detection",
        "--enable-unsafe-swiftshader",
        "--metrics-recording-only",
        "--password-store=basic",
        "--use-mock-keychain",
        "--lang=%s" % ((persona.get("languagesZ") or ["en-US"])[0]),
    ]
    args.extend(proxy_args(proxy))
    if headless:
        args.append("--headless=new")
    args.extend(extra_args)
    args.append("about:blank")

    process = subprocess.Popen(
        args,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        preexec_fn=_child_setup,
        # 3 and 4 must survive CPython's fd sweep, which runs *after*
        # preexec_fn; without them Chrome reports "pipe descriptors are not open".
        pass_fds=(cmd_read, out_write, 3, 4),
    )
    os.close(cmd_read)
    os.close(out_write)

    cdp = PipeCDP(process, out_read, cmd_write)
    try:
        cdp.call("Browser.getVersion", timeout=25)
    except CDPError as exc:
        process.kill()
        cdp.close()
        shutil.rmtree(profile_dir, ignore_errors=True)
        raise LaunchError("browser did not answer on the debugging pipe: %s" % exc) from exc

    # Branded Chrome 137+ silently ignores --load-extension, so mount the
    # unpacked extension over CDP instead. This is the supported path and it
    # also reports the generated extension id.
    extension_id = None
    extension_error = None
    if extension:
        last_error: Optional[BaseException] = None
        # The first call races the extension service starting up, so retry.
        for attempt in range(5):
            try:
                loaded = cdp.call("Extensions.loadUnpacked", {"path": str(extension)}, timeout=20)
                extension_id = loaded.get("id")
                break
            except CDPError as exc:
                last_error = exc
                time.sleep(0.25 * (attempt + 1))
        if extension_id is None:
            extension_error = str(last_error)

    try:
        targets = cdp.call("Target.getTargets")["targetInfos"]
        page = next((t for t in targets if t.get("type") == "page"), None)
        if page is None:
            created = cdp.call("Target.createTarget", {"url": "about:blank"})
            target_id = created["targetId"]
        else:
            target_id = page["targetId"]

        attached = cdp.call("Target.attachToTarget", {"targetId": target_id, "flatten": True})
        session_id = attached["sessionId"]

        cdp.call("Page.enable", session_id=session_id)
        cdp.call("Runtime.enable", session_id=session_id)

        cdp.call(
            "Emulation.setUserAgentOverride",
            {
                "userAgent": persona.get("ua") or "",
                "acceptLanguage": ",".join(persona.get("languagesZ") or ["en-US"]),
                "platform": persona.get("platformKey") or "Win32",
                "userAgentMetadata": user_agent_metadata(persona),
            },
            session_id=session_id,
        )
        cdp.call(
            "Emulation.setDeviceMetricsOverride",
            {
                "width": int(persona.get("screenX") or 1920),
                "height": int(persona.get("screenY") or 1080),
                "deviceScaleFactor": float(persona.get("pixelRatio") or 1.0),
                "mobile": bool((persona.get("userAgentData") or {}).get("mobile")),
                "screenWidth": int(persona.get("screenX") or 1920),
                "screenHeight": int(persona.get("screenY") or 1080),
            },
            session_id=session_id,
        )
        if persona.get("timezone"):
            cdp.call("Emulation.setTimezoneOverride", {"timezoneId": persona["timezone"]}, session_id=session_id)
        if persona.get("languagesZ"):
            cdp.call("Emulation.setLocaleOverride", {"locale": persona["languagesZ"][0]}, session_id=session_id)
        cdp.call(
            "Page.addScriptToEvaluateOnNewDocument",
            {"source": source},
            session_id=session_id,
        )
    except CDPError as exc:
        try:
            cdp.call("Browser.close", timeout=3)
        except CDPError:
            process.kill()
        cdp.close()
        shutil.rmtree(profile_dir, ignore_errors=True)
        raise LaunchError("could not configure the browser: %s" % exc) from exc

    session = Session(process, cdp, profile_dir, session_id, extension_id, extension_error)

    # When the extension is mounted, its own module is what decides the route:
    # a proxy stored on a *different* persona must not fight the one just
    # launched, so the launched persona is written back through the extension
    # before the first navigation. The worker may not exist until a navigation
    # happens, in which case the --proxy-server flag covers the first request
    # and the caller can apply it again once the worker is alive.
    if extension_id:
        try:
            session.apply_extension_network(persona, timeout=3.0)
        except (LaunchError, CDPError):
            session.extension_network = None

    if url and url != "about:blank":
        session.goto(url)
    return session


# --------------------------------------------------------------------------
# verification
# --------------------------------------------------------------------------

PROBE_JS = r"""
(async () => {
  function hashString(str) {
    let h = 2166136261;
    for (let i = 0; i < str.length; i++) { h ^= str.charCodeAt(i); h = Math.imul(h, 16777619); }
    return h >>> 0;
  }
  const canvas = document.createElement('canvas');
  canvas.width = 220; canvas.height = 60;
  const ctx = canvas.getContext('2d');
  ctx.textBaseline = 'top';
  ctx.font = '14px Arial';
  ctx.fillStyle = '#f60';
  ctx.fillRect(0, 0, 100, 20);
  ctx.fillStyle = '#069';
  ctx.fillText('fp-spoof probe', 4, 22);

  const glCanvas = document.createElement('canvas');
  const gl = glCanvas.getContext('webgl');
  const uad = navigator.userAgentData;
  let nativeOk = false;
  try {
    const desc = Object.getOwnPropertyDescriptor(Navigator.prototype, 'userAgent');
    nativeOk = !!desc && !!desc.get && /\[native code\]/.test(Function.prototype.toString.call(desc.get));
  } catch (e) { nativeOk = false; }

  let highEntropy = null;
  try {
    if (uad && typeof uad.getHighEntropyValues === 'function') {
      const values = await uad.getHighEntropyValues(['architecture', 'bitness', 'platformVersion', 'uaFullVersion']);
      highEntropy = [values.architecture, values.bitness, values.platformVersion, values.uaFullVersion].join('|');
    }
  } catch (e) { highEntropy = null; }

  let audioHash = null;
  try {
    const ctx = new OfflineAudioContext(1, 128, 44100);
    const analyser = ctx.createAnalyser();
    analyser.fftSize = 256;
    const bytes = new Uint8Array(analyser.frequencyBinCount);
    analyser.getByteFrequencyData(bytes);
    audioHash = hashString(Array.prototype.join.call(bytes, ','));
  } catch (e) { audioHash = null; }

  let geo = null;
  try {
    if (navigator.geolocation) {
      geo = await new Promise((resolve) => {
        const timer = setTimeout(() => resolve(null), 1500);
        navigator.geolocation.getCurrentPosition(
          (position) => { clearTimeout(timer); resolve([position.coords.latitude, position.coords.longitude]); },
          () => { clearTimeout(timer); resolve(null); },
          { timeout: 1200 }
        );
      });
    }
  } catch (e) { geo = null; }

  return {
    ua: navigator.userAgent,
    platform: navigator.platform,
    hardwareConcurrency: navigator.hardwareConcurrency,
    deviceMemory: navigator.deviceMemory === undefined ? null : navigator.deviceMemory,
    languages: (navigator.languages || []).join(','),
    maxTouchPoints: navigator.maxTouchPoints,
    webdriver: navigator.webdriver,
    screenW: screen.width,
    screenH: screen.height,
    availW: screen.availWidth,
    availH: screen.availHeight,
    dpr: window.devicePixelRatio,
    timezone: Intl.DateTimeFormat().resolvedOptions().timeZone,
    tzOffset: new Date('2024-01-15T12:00:00Z').getTimezoneOffset(),
    resolvedLocale: Intl.DateTimeFormat().resolvedOptions().locale,
    audioHash: audioHash,
    glVendor: gl ? gl.getParameter(37445) : null,
    glRenderer: gl ? gl.getParameter(37446) : null,
    uadBrands: uad ? uad.brands.map(b => b.brand + '/' + b.version).join(',') : null,
    uadPlatform: uad ? uad.platform : null,
    highEntropy: highEntropy,
    nativeToString: nativeOk,
    canvasHash: hashString(String.fromCharCode.apply(null, ctx.getImageData(0, 0, 220, 60).data)),
    dataUrlHash: hashString(canvas.toDataURL()),
    pluginsLength: navigator.plugins ? navigator.plugins.length : 0,
    earlyUserAgent: typeof window.__EARLY_UA__ === 'string' ? window.__EARLY_UA__ : null,
    geoLat: geo ? geo[0] : null,
    geoLon: geo ? geo[1] : null
  };
})()
"""


class _ProbeServer:
    """Tiny local server: serves a page and records the request headers."""

    def __init__(self) -> None:
        self.headers: Dict[str, str] = {}
        self._httpd: Optional[http.server.ThreadingHTTPServer] = None
        self._thread: Optional[threading.Thread] = None

    def start(self) -> "_ProbeServer":
        outer = self

        class Handler(http.server.BaseHTTPRequestHandler):
            protocol_version = "HTTP/1.1"

            def log_message(self, *args: Any) -> None:  # noqa: D401 - silence
                return

            def do_GET(self) -> None:
                outer.headers = {k.lower(): v for k, v in self.headers.items()}
                body = (
                    b"<!doctype html><html><head><meta charset='utf-8'>"
                    b"<script>window.__EARLY_UA__ = navigator.userAgent;</script>"
                    b"<title>fp-spoof probe</title></head><body>"
                    b"<canvas width='220' height='60'></canvas></body></html>"
                )
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Cache-Control", "no-store")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

        self._httpd = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self._thread = threading.Thread(target=self._httpd.serve_forever, daemon=True)
        self._thread.start()
        return self

    @property
    def url(self) -> str:
        assert self._httpd is not None
        host, port = self._httpd.server_address[:2]
        return "http://%s:%d/" % (host, port)

    def stop(self) -> None:
        if self._httpd is not None:
            self._httpd.shutdown()
            self._httpd.server_close()
            self._httpd = None


def _check(name: str, expected: Any, actual: Any) -> Dict[str, Any]:
    """Compare two observations, tolerating int/float rendering differences."""
    ok = str(expected) == str(actual)
    if not ok and isinstance(expected, (int, float)) and isinstance(actual, (int, float)):
        ok = float(expected) == float(actual)
    return {"name": name, "expected": expected, "actual": actual, "ok": ok}


def verify_persona(
    persona: Dict[str, Any],
    chrome: Optional[str] = None,
    headless: bool = True,
    other_persona: Optional[Dict[str, Any]] = None,
    extension: Optional[str] = None,
    proxy: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Apply ``persona`` in a real browser and compare observed vs expected."""
    server = _ProbeServer().start()
    checks: List[Dict[str, Any]] = []
    try:
        session = launch(persona, url=server.url, headless=headless, chrome=chrome,
                         extension=extension, proxy=proxy or persona.get("proxy"))
        try:
            if extension:
                # Give the service worker a moment to install its DNR header
                # rules, then re-request so the captured headers reflect them.
                time.sleep(1.5)
                session.goto(server.url)
            observed = session.evaluate(PROBE_JS)
            repeat = session.evaluate(PROBE_JS)
            session.reload()
            after_reload = session.evaluate(PROBE_JS)
        finally:
            session.close()

        headers = dict(server.headers)
    finally:
        server.stop()

    if not isinstance(observed, dict):
        raise LaunchError("probe returned no data (got %r)" % (observed,))

    uad = persona.get("userAgentData") or {}
    languages = persona.get("languagesZ") or []

    checks.append(_check("http user-agent", persona.get("ua"), headers.get("user-agent")))
    checks.append(_check("navigator.userAgent", persona.get("ua"), observed.get("ua")))
    checks.append(_check("navigator.platform", persona.get("platformKey"), observed.get("platform")))
    checks.append(_check("hardwareConcurrency", persona.get("hardwareConcurrency"), observed.get("hardwareConcurrency")))
    checks.append(_check("deviceMemory", persona.get("deviceMemory"), observed.get("deviceMemory")))
    checks.append(_check("languages", ",".join(languages), observed.get("languages")))
    checks.append(_check("Intl resolved locale", languages[0] if languages else None,
                        observed.get("resolvedLocale")))
    checks.append(_check("maxTouchPoints", persona.get("maxTouchPoints"), observed.get("maxTouchPoints")))
    checks.append(_check("webdriver flag", False, observed.get("webdriver")))
    checks.append(_check("screen.width", persona.get("screenX"), observed.get("screenW")))
    checks.append(_check("screen.height", persona.get("screenY"), observed.get("screenH")))
    checks.append(_check("screen.availHeight", persona.get("availY"), observed.get("availH")))
    checks.append(_check("devicePixelRatio", persona.get("pixelRatio"), observed.get("dpr")))
    checks.append(_check("timezone", persona.get("timezone"), observed.get("timezone")))
    checks.append(_check("webgl vendor", persona.get("webglVendor"), observed.get("glVendor")))
    checks.append(_check("webgl renderer", persona.get("webglRenderer"), observed.get("glRenderer")))
    checks.append(_check("plugins.length", len(persona.get("plugins") or ()), observed.get("pluginsLength")))
    checks.append(_check("native toString", True, observed.get("nativeToString")))

    expected_geo = persona.get("geo") or {}
    if expected_geo:
        checks.append(_check(
            "geolocation latitude",
            round(float(expected_geo.get("latitude")), 4),
            None if observed.get("geoLat") is None else round(float(observed["geoLat"]), 4),
        ))
        checks.append(_check(
            "geolocation longitude",
            round(float(expected_geo.get("longitude")), 4),
            None if observed.get("geoLon") is None else round(float(observed["geoLon"]), 4),
        ))

    if extension:
        # The probe page records navigator.userAgent from the first inline
        # <script> in <head>. Only a document_start content script beats it.
        checks.append(_check(
            "UA at document_start", persona.get("ua"), observed.get("earlyUserAgent")
        ))

    brand_string = ",".join("%s/%s" % (b.get("brand"), b.get("version")) for b in uad.get("brands") or [])
    if brand_string:
        checks.append(_check("userAgentData.brands", brand_string, observed.get("uadBrands")))
    if uad.get("platformVersion"):
        expected_high = "|".join([
            str(uad.get("architecture") or "x86"),
            str(uad.get("bitness") or "64"),
            str(uad.get("platformVersion")),
            str(persona.get("version") or ""),
        ])
        checks.append(_check("high entropy values", expected_high, observed.get("highEntropy")))

    # Client hints travel as headers. Chrome sends them on secure origins
    # (127.0.0.1 counts); Safari never sends them at all, so "absent" is the
    # correct outcome for a Safari persona rather than a failure.
    expects_hints = str(persona.get("browser")) in ("chrome", "edge")
    checks.append(_check(
        "sec-ch-ua header",
        "present" if expects_hints else "absent",
        "present" if headers.get("sec-ch-ua") else "absent",
    ))
    if expects_hints and headers.get("sec-ch-ua") and uad.get("brands"):
        brands = uad["brands"]
        checks.append(_check(
            "sec-ch-ua content",
            "yes",
            "yes" if any(b.get("brand") in headers["sec-ch-ua"] for b in brands) else "no",
        ))

    # Deterministic canvas noise: same persona must yield the same pixels on
    # repeated reads and across reloads.
    checks.append(_check("canvas stable (repeat)", observed.get("canvasHash"), repeat.get("canvasHash")))
    checks.append(_check("canvas stable (reload)", observed.get("canvasHash"), after_reload.get("canvasHash")))
    checks.append(_check("dataURL stable", observed.get("dataUrlHash"), repeat.get("dataUrlHash")))
    checks.append(_check("audio stable (repeat)", observed.get("audioHash"), repeat.get("audioHash")))
    checks.append(_check("audio stable (reload)", observed.get("audioHash"), after_reload.get("audioHash")))

    if other_persona:
        other_server = _ProbeServer().start()
        try:
            other = launch(other_persona, url=other_server.url, headless=headless, chrome=chrome,
                           extension=extension, proxy=other_persona.get("proxy"))
            try:
                other_observed = other.evaluate(PROBE_JS)
            finally:
                other.close()
        finally:
            other_server.stop()
        if isinstance(other_observed, dict):
            checks.append(_check(
                "canvas differs per persona",
                "different",
                "different" if other_observed.get("canvasHash") != observed.get("canvasHash") else "same",
            ))
            checks.append(_check(
                "audio differs per persona",
                "different",
                "different" if other_observed.get("audioHash") != observed.get("audioHash") else "same",
            ))

    return {
        "persona": {k: v for k, v in persona.items() if k in ("browser", "platform", "version", "ua")},
        "checks": checks,
        "observed": observed,
        "headers": {k: v for k, v in headers.items() if k in ("user-agent", "sec-ch-ua", "accept-language")},
        "passed": all(c["ok"] for c in checks),
    }
