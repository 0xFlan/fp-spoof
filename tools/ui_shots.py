"""Rasterise the extension UI for visual review.

Headless Chrome, extension mounted, one PNG per surface x scheme x viewport,
plus 2x-DPR crops of the sticky bar, a field-row block and the footer actions so
hairline weight and baseline rhythm are actually judgeable.

    .venv/bin/python tools/ui_shots.py [--headful] [--out DIR]

Writes a manifest.json next to the images so the pytest render suite can reuse
the same geometry without parsing pixels.
"""

from __future__ import annotations

import argparse
import base64
import json
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

from launcher.launch import LaunchError, launch  # noqa: E402

EXTENSION = REPO / "extension"
MIRROR = json.loads((EXTENSION / "personas.json").read_text())
PERSONA = MIRROR["personas"][MIRROR["default"]]


def open_tab(session, url, width, height, scheme):
    target = session.cdp.call("Target.createTarget", {"url": "about:blank"})
    sid = session.cdp.call(
        "Target.attachToTarget", {"targetId": target["targetId"], "flatten": True}
    )["sessionId"]
    session.cdp.call("Page.enable", {}, session_id=sid)
    session.cdp.call("Runtime.enable", {}, session_id=sid)
    session.cdp.call(
        "Emulation.setDeviceMetricsOverride",
        {"width": width, "height": height, "deviceScaleFactor": 1, "mobile": False},
        session_id=sid,
    )
    session.cdp.call(
        "Emulation.setEmulatedMedia",
        {"features": [{"name": "prefers-color-scheme", "value": scheme}]},
        session_id=sid,
    )
    session.cdp.call("Page.navigate", {"url": url}, session_id=sid)
    time.sleep(2.2)
    return sid


def evaluate(session, sid, expression):
    return session.cdp.evaluate(expression, session_id=sid, await_promise=True)


def shoot(session, sid, path, clip=None):
    params = {"format": "png", "captureBeyondViewport": False}
    if clip:
        params["clip"] = dict(clip, scale=2)
    data = session.cdp.call("Page.captureScreenshot", params, session_id=sid)["data"]
    path.write_bytes(base64.b64decode(data))
    return path


GEOMETRY_JS = """(() => {
  const rect = (sel) => {
    const el = document.querySelector(sel);
    if (!el) return null;
    const r = el.getBoundingClientRect();
    return { x: Math.round(r.x), y: Math.round(r.y + window.scrollY),
             w: Math.round(r.width), h: Math.round(r.height) };
  };
  return JSON.stringify({
    scrollHeight: document.documentElement.scrollHeight,
    bar: rect('.topbar') || rect('header'),
    rows: rect('.card:nth-of-type(2)'),
    footer: rect('.danger') || rect('.actions')
  });
})()"""


def shoot_all(session, outdir, headful=False):
    outdir.mkdir(parents=True, exist_ok=True)
    manifest = {"extension": session.extension_id, "shots": [], "crops": []}

    surfaces = [
        ("popup", "src/popup.html", 360, 620),
        ("editor-1280", "src/options.html", 1280, 1500),
        ("editor-900", "src/options.html", 900, 1500),
    ]

    for scheme in ("light", "dark"):
        for name, page, width, height in surfaces:
            url = "chrome-extension://%s/%s" % (session.extension_id, page)
            sid = open_tab(session, url, width, height, scheme)

            # Height the document actually needs, measured at the final width,
            # so the PNG has no dead space below the last section.
            content_js = ("Math.ceil(document.body.getBoundingClientRect().height)"
                          if name == "popup" else
                          "Math.ceil(document.querySelector('main').getBoundingClientRect().bottom"
                          " + document.querySelector('.layout').getBoundingClientRect().top + 40)")
            floor = 320 if name == "popup" else 700
            doc_height = min(max(int(evaluate(session, sid, content_js)), floor), 4000)
            info = json.loads(evaluate(session, sid, GEOMETRY_JS))
            session.cdp.call(
                "Emulation.setDeviceMetricsOverride",
                {"width": width, "height": doc_height, "deviceScaleFactor": 1, "mobile": False},
                session_id=sid,
            )
            time.sleep(0.6)
            info = json.loads(evaluate(session, sid, GEOMETRY_JS))

            shot = outdir / ("%s-%s.png" % (name, scheme))
            shoot(session, sid, shot)
            manifest["shots"].append(
                {"surface": name, "scheme": scheme, "width": width,
                 "height": doc_height, "path": str(shot.relative_to(REPO)),
                 "geometry": info}
            )

            # 2x crops: sticky bar, a block of field rows, the footer actions.
            regions = [("bar", info.get("bar")), ("rows", info.get("rows")),
                       ("footer", info.get("footer"))]
            for label, box in regions:
                if not box or box["w"] < 40 or box["h"] < 8:
                    continue
                crop = outdir / ("crop-%s-%s-%s-2x.png" % (name, label, scheme))
                shoot(session, sid, crop, clip={
                    "x": box["x"], "y": box["y"], "width": box["w"],
                    "height": min(box["h"], 420),
                })
                manifest["crops"].append(
                    {"surface": name, "scheme": scheme, "region": label,
                     "path": str(crop.relative_to(REPO))}
                )

    (outdir / "manifest.json").write_text(json.dumps(manifest, indent=2))
    return manifest


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", default=str(REPO / "artifacts" / "ui"))  # resolved below
    parser.add_argument("--headful", action="store_true", help="fallback if headless cannot mount the extension")
    args = parser.parse_args(argv)

    try:
        session = launch(PERSONA, url="about:blank", headless=not args.headful,
                         extension=str(EXTENSION))
    except LaunchError as exc:
        print("error: %s" % exc, file=sys.stderr)
        return 1
    try:
        if not session.extension_id:
            print("error: extension did not mount (%s)" % (session.extension_error or "unknown"),
                  file=sys.stderr)
            return 2
        manifest = shoot_all(session, Path(args.out).resolve(), headful=args.headful)
    finally:
        session.close()

    print("extension %s" % manifest["extension"])
    for shot in manifest["shots"]:
        print("shot %-12s %-6s %4dx%-5d %s" % (
            shot["surface"], shot["scheme"], shot["width"], shot["height"], shot["path"]))
    print("%d crops written to %s" % (len(manifest["crops"]), args.out))
    return 0


if __name__ == "__main__":
    sys.exit(main())
