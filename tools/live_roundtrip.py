"""Export -> import -> re-export against a real Chrome with the extension loaded.

Everything here runs the extension's own code: the options page, the worker's
importProfile handler, storage, and the injected patch. The script only drives
CDP and reads what the page reports.
"""

import json
import random
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from fpr.fingerprint import gen
from launcher.launch import chrome_path, launch

ROOT = Path(__file__).resolve().parent.parent
EXTENSION = ROOT / "extension"
DERIVED = {"availX", "availY", "touchPoints", "orientation"}

PROBE = b"""<!doctype html><html><head><meta charset='utf-8'><script>
window.__EARLY__ = navigator.userAgent;
</script></head><body><canvas id='c' width='200' height='60'></canvas></body></html>"""


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *args):
        return

    def do_GET(self):
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(PROBE)))
        self.end_headers()
        self.wfile.write(PROBE)


def serve():
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    return httpd, "http://127.0.0.1:%d/" % httpd.server_port


def wait_ready(session, timeout=15.0):
    deadline = __import__("time").time() + timeout
    while __import__("time").time() < deadline:
        try:
            if session.evaluate("document.readyState") == "complete":
                return True
        except Exception:
            pass
        __import__("time").sleep(0.2)
    return False


def send_import(session, text):
    return session.evaluate(
        "(async () => await new Promise((resolve) => chrome.runtime.sendMessage("
        "{type: 'importProfile', text: %s}, resolve)))()" % json.dumps(text)
    )


def storage(session):
    return session.evaluate(
        "(async () => { const s = await chrome.storage.local.get(null);"
        " return { active: s.active || null, imports: Object.keys(s.imports || {}),"
        " bytes: JSON.stringify(s.imports || {}).length }; })()"
    )


def page_values(session, url):
    session.goto(url)
    wait_ready(session)
    return session.evaluate(
        "(() => {"
        " const gl = document.createElement('canvas').getContext('webgl');"
        " const ext = gl && gl.getExtension('WEBGL_debug_renderer_info');"
        " const c = document.getElementById('c'); const ctx = c.getContext('2d');"
        " ctx.fillText('fp-spoof', 10, 30);"
        " const hash = (s) => { let h = 0; for (let i = 0; i < s.length; i++) h = (h * 31 + s.charCodeAt(i)) | 0; return h; };"
        " return { ua: navigator.userAgent, early: window.__EARLY__ || null,"
        "  screenX: screen.width, screenY: screen.height, dpr: devicePixelRatio,"
        "  tz: Intl.DateTimeFormat().resolvedOptions().timeZone,"
        "  renderer: ext ? gl.getParameter(ext.UNMASKED_RENDERER_WEBGL) : null,"
        "  vendor: ext ? gl.getParameter(ext.UNMASKED_VENDOR_WEBGL) : null,"
        "  seed: window.__FPS_PERSONA__ ? window.__FPS_PERSONA__.canvasSeed : null,"
        "  canvas: hash(c.toDataURL()), dataURL: c.toDataURL().length };"
        "})()"
    )


def main():
    persona = gen(random.Random(11), "chrome", "windows")
    httpd, url = serve()
    session = None
    try:
        session = launch(persona, url="about:blank", headless=True,
                         chrome=chrome_path(), extension=str(EXTENSION))
        print("extension id:", session.extension_id)
        options = "chrome-extension://%s/src/options.html" % session.extension_id
        name = "roundtrip"

        session.goto(options)
        wait_ready(session)
        sent = send_import(session, json.dumps({"personas": {name: persona}}))
        print("import:", sent)
        if not sent.get("ok"):
            print("FAIL: import refused the exported persona")
            return 1
        after_import = storage(session)
        print("storage after import:", after_import)

        # popup-close / reopen equivalent: leave the page entirely, come back
        session.goto("about:blank")
        session.goto(options)
        wait_ready(session)
        after_reopen = storage(session)
        print("storage after reopen:", after_reopen)
        if name not in after_reopen["imports"] or after_reopen["active"] != name:
            print("FAIL: import did not survive leaving the page")
            return 1

        observed = page_values(session, url)
        print("page:", json.dumps({k: observed[k] for k in
              ("ua", "early", "screenX", "screenY", "dpr", "tz", "renderer", "seed")}, indent=2))
        expected_ok = (
            observed["ua"] == persona["ua"]
            and observed["early"] == persona["ua"]
            and observed["screenX"] == persona["screenX"]
            and observed["screenY"] == persona["screenY"]
            and observed["dpr"] == persona["pixelRatio"]
            and observed["tz"] == persona["timezone"]
            and observed["seed"] == persona["canvasSeed"]
            and "SwiftShader" not in str(observed["renderer"])
        )
        print("injected matches persona:", expected_ok)

        # re-export through the real button, capturing the blob it creates
        session.goto(options)
        wait_ready(session)
        import time
        # The page resolves its draft asynchronously; export before that writes null.
        applied = None
        for _ in range(60):
            applied = session.evaluate("document.querySelector('#ap-name').textContent")
            if applied == name:
                break
            time.sleep(0.2)
        print("Applied card after reopen:", applied)
        if applied != name:
            print("FAIL: reopened editor did not resolve the imported persona")
            return 1
        import glob
        import tempfile
        download_dir = tempfile.mkdtemp(prefix="fps-export-")
        for method in ("Browser.setDownloadBehavior", "Page.setDownloadBehavior"):
            try:
                session.cdp.call(method, {"behavior": "allow", "downloadPath": download_dir})
                break
            except Exception:
                continue
        session.evaluate("document.querySelector('#export').click()")
        files = []
        for _ in range(50):
            files = glob.glob(download_dir + "/*.json")
            if files:
                break
            time.sleep(0.2)
        if not files:
            print("FAIL: export produced no file")
            return 1
        exported = Path(files[0]).read_text()
        print("exported file:", Path(files[0]).name)
        print("re-export bytes:", len(exported or ""))
        if not exported:
            print("FAIL: export produced nothing")
            return 1
        again = json.loads(exported)
        # Compare the JSON each side actually carries: generator values may be
        # tuples, while a JSON round trip always yields lists.
        def canonical(value):
            # JSON round trip: tuples become lists, int/float compare by value.
            return json.loads(json.dumps(value, sort_keys=True))

        diffs = [key for key in persona if key not in DERIVED and
                 canonical(again.get(key)) != canonical(persona[key])]
        if diffs:
            for key in diffs:
                print("DIFF", key, "original=", json.dumps(persona[key])[:120],
                      "exported=", json.dumps(again.get(key))[:120])
        print("name in Applied card:", session.evaluate("document.querySelector('#ap-name').textContent"))
        print("field differences (excluding derived):", diffs)
        print("plugins equal as JSON:", json.dumps(persona.get("plugins")) == json.dumps(again.get("plugins")))
        print("plugins original:", json.dumps(persona.get("plugins")))
        print("plugins exported:", json.dumps(again.get("plugins")))

        print("derived recomputed:", {k: again.get(k) for k in ("availX", "availY", "touchPoints")})

        # live refusals must change nothing
        before = storage(session)
        bad_value = dict(persona, pixelRatio=9)
        refused = send_import(session, json.dumps({"personas": {"bad": bad_value}}))
        malformed = send_import(session, "{not json")
        print("refused out-of-range:", refused.get("error"))
        print("refused malformed:", malformed.get("error"))
        after = storage(session)
        print("storage unchanged after refusals:", before == after)
        unchanged_page = page_values(session, url)
        print("page unchanged after refusals:", unchanged_page["ua"] == observed["ua"])

        ok = expected_ok and not diffs and before == after and \
            unchanged_page["ua"] == observed["ua"] and \
            "pixelRatio" in str(refused.get("error")) and \
            "not valid JSON" in str(malformed.get("error"))
        print("RESULT:", "PASS" if ok else "FAIL")
        return 0 if ok else 1
    finally:
        if session is not None:
            session.close()
        httpd.shutdown()


if __name__ == "__main__":
    sys.exit(main())
