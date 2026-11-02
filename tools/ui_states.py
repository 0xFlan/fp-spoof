"""Rasterise interaction states through real CDP input.

Hover comes from Input.dispatchMouseEvent, :focus-visible from dispatching Tab
key events (a DOM .focus() would not raise the keyboard ring), :active from
holding a mouse button down. Also builds a per-surface contact sheet by
rendering the crops into an HTML grid in the same browser - no image library
needed.

    .venv/bin/python tools/ui_states.py
"""

from __future__ import annotations

import base64
import json
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

from launcher.launch import launch  # noqa: E402
from ui_shots import EXTENSION, PERSONA, evaluate, open_tab, shoot  # noqa: E402

OUT = REPO / "artifacts" / "ui"
TAB = {"key": "Tab", "code": "Tab", "windowsVirtualKeyCode": 9, "nativeVirtualKeyCode": 9}


def rect(session, sid, selector):
    data = evaluate(session, sid, """(() => {
      const el = document.querySelector(%s);
      if (!el) return null;
      const r = el.getBoundingClientRect();
      return { x: r.x, y: r.y, w: r.width, h: r.height };
    })()""" % json.dumps(selector))
    return json.loads(data) if isinstance(data, str) else data


def page_box(session, sid, selector):
    """CDP clips are in page coordinates while input events are in viewport
    ones. Using the viewport rect for a clip silently produced blank crops for
    every control below the fold."""
    box = rect(session, sid, selector)
    if not box:
        return None
    offset = json.loads(evaluate(session, sid, "JSON.stringify({x: scrollX, y: scrollY})"))
    return {"x": box["x"] + offset["x"], "y": box["y"] + offset["y"],
            "w": box["w"], "h": box["h"]}


def shoot_state(session, sid, path, box, pad=14):
    """2x crop of one control in page space; captureBeyondViewport keeps
    scrolled-out controls from coming back empty."""
    if not box:
        return None
    clip = {"x": max(box["x"] - pad, 0), "y": max(box["y"] - pad, 0),
            "width": box["w"] + pad * 2, "height": min(box["h"] + pad * 2, 320), "scale": 2}
    data = session.cdp.call("Page.captureScreenshot",
                            {"format": "png", "captureBeyondViewport": True, "clip": clip},
                            session_id=sid)["data"]
    path.write_bytes(base64.b64decode(data))
    return path


def move(session, sid, selector):
    box = rect(session, sid, selector)
    if not box:
        return None
    x, y = box["x"] + box["w"] / 2, box["y"] + box["h"] / 2
    session.cdp.call("Input.dispatchMouseEvent",
                     {"type": "mouseMoved", "x": x, "y": y, "button": "none", "buttons": 0},
                     session_id=sid)
    time.sleep(0.18)
    return box


def press(session, sid, selector):
    box = move(session, sid, selector)
    if not box:
        return None
    x, y = box["x"] + box["w"] / 2, box["y"] + box["h"] / 2
    session.cdp.call("Input.dispatchMouseEvent",
                     {"type": "mousePressed", "x": x, "y": y, "button": "left",
                      "buttons": 1, "clickCount": 1}, session_id=sid)
    time.sleep(0.18)
    return box


def release(session, sid, selector):
    box = rect(session, sid, selector)
    if not box:
        return
    x, y = box["x"] + box["w"] / 2, box["y"] + box["h"] / 2
    session.cdp.call("Input.dispatchMouseEvent",
                     {"type": "mouseReleased", "x": x, "y": y, "button": "left",
                      "buttons": 0, "clickCount": 1}, session_id=sid)
    time.sleep(0.1)


def park(session, sid):
    """Move the pointer off every control so the next crop is truly resting."""
    session.cdp.call("Input.dispatchMouseEvent",
                     {"type": "mouseMoved", "x": 3, "y": 3, "button": "none", "buttons": 0},
                     session_id=sid)
    time.sleep(0.12)


def scroll_into(session, sid, selector):
    """Controls below the fold never receive input events, which silently
    produced blank crops. Centre the target first, every time."""
    evaluate(session, sid, "(() => { const el = document.querySelector(%s);"
                           " if (el) el.scrollIntoView({block: 'center'}); return 1; })()"
             % json.dumps(selector))
    time.sleep(0.18)


def reset_state(session, sid):
    """Per-shot determinism: a pin toggled by an :active release otherwise
    leaks into every later capture."""
    evaluate(session, sid, "chrome.storage.local.clear()")
    session.cdp.call("Page.reload", {}, session_id=sid)
    time.sleep(2.0)


def tab_to(session, sid, selector, limit=90):
    """Walk the real focus order until the wanted control owns focus."""
    evaluate(session, sid, """(() => {
      const active = document.activeElement;
      if (active && active.blur) active.blur();
      document.body.setAttribute('tabindex', '-1');
      document.body.focus();
      return document.activeElement.tagName;
    })()""")
    for index in range(limit):
        session.cdp.call("Input.dispatchKeyEvent", dict(TAB, type="keyDown"), session_id=sid)
        session.cdp.call("Input.dispatchKeyEvent", dict(TAB, type="keyUp"), session_id=sid)
        time.sleep(0.03)
        hit = evaluate(session, sid,
                       "!!(document.activeElement && document.activeElement.matches(%s))"
                       % json.dumps(selector))
        if hit:
            return index + 1
    return None


def crop_around(box, pad=14, height=None):
    return {"x": max(box["x"] - pad, 0), "y": max(box["y"] - pad, 0),
            "width": box["w"] + pad * 2, "height": min(height or box["h"] + pad * 2, 260)}


def sheet(entries, path, scheme):
    bg, fg = ("#ffffff", "#1d1d1f") if scheme == "light" else ("#000000", "#f5f5f7")
    cells = []
    for label, name in entries:
        cells.append(
            '<figure><figcaption>%s</figcaption>'
            '<img src="%s"></figure>' % (label, (OUT / name).as_uri()))
    html = ("<!doctype html><meta charset=utf-8><style>"
            "body{margin:0;padding:20px;background:%s;color:%s;"
            "font:13px -apple-system,BlinkMacSystemFont,sans-serif}"
            "figure{margin:0 0 18px}"
            "figcaption{font-size:11px;opacity:.6;margin:0 0 6px}"
            "img{display:block;max-width:980px;border-radius:8px}</style>"
            "<body>%s</body>" % (bg, fg, "".join(cells)))
    html_path = OUT / (path.replace(".png", ".html"))
    html_path.write_text(html)
    return html_path


def capture_surface(session, name, page, width, height, scheme):
    url = "chrome-extension://%s/%s" % (session.extension_id, page)
    sid = open_tab(session, url, width, height, scheme)
    reset_state(session, sid)
    entries = []

    # rest/hover pairs, so the judge sees the delta rather than one state alone
    for label, selector in HOVER:
        scroll_into(session, sid, selector)
        rest = "state-%s-rest-%s-%s.png" % (name, label, scheme)
        shoot_state(session, sid, OUT / rest, page_box(session, sid, selector))
        entries.append(("rest %s (%s)" % (label, selector), rest))

        move(session, sid, selector)
        hover = "state-%s-hover-%s-%s.png" % (name, label, scheme)
        shoot_state(session, sid, OUT / hover, page_box(session, sid, selector))
        entries.append(("hover %s (%s)" % (label, selector), hover))
        park(session, sid)

    for label, selector in FOCUS:
        scroll_into(session, sid, selector)
        if tab_to(session, sid, selector):
            name_file = "state-%s-focus-%s-%s.png" % (name, label, scheme)
            shoot_state(session, sid, OUT / name_file, page_box(session, sid, selector))
            entries.append(("focus-visible %s (%s)" % (label, selector), name_file))

    full = "state-%s-context-%s.png" % (name, scheme)
    scroll_into(session, sid, FOCUS[0][1])
    if tab_to(session, sid, FOCUS[0][1]):
        shoot(session, sid, OUT / full)
        entries.append(("keyboard focus on %s, full surface" % FOCUS[0][0], full))

    for label, selector in ACTIVE:
        scroll_into(session, sid, selector)
        if press(session, sid, selector):
            name_file = "state-%s-active-%s-%s.png" % (name, label, scheme)
            shoot_state(session, sid, OUT / name_file, page_box(session, sid, selector))
            entries.append(("active %s (%s), button held" % (label, selector), name_file))
            release(session, sid, selector)
            park(session, sid)

    html_path = sheet(entries, "sheet-%s-%s.png" % (name, scheme), scheme)
    target = session.cdp.call("Target.createTarget", {"url": html_path.as_uri()})
    ssid = session.cdp.call("Target.attachToTarget",
                            {"targetId": target["targetId"], "flatten": True})["sessionId"]
    session.cdp.call("Page.enable", {}, session_id=ssid)
    session.cdp.call("Runtime.enable", {}, session_id=ssid)
    session.cdp.call("Emulation.setDeviceMetricsOverride",
                     {"width": 1020, "height": 900, "deviceScaleFactor": 1, "mobile": False},
                     session_id=ssid)
    time.sleep(1.0)
    doc = int(evaluate(session, ssid, "Math.ceil(document.body.getBoundingClientRect().height)"))
    session.cdp.call("Emulation.setDeviceMetricsOverride",
                     {"width": 1020, "height": min(doc, 6000), "deviceScaleFactor": 1,
                      "mobile": False}, session_id=ssid)
    time.sleep(0.5)
    shoot(session, ssid, OUT / path_for(name, scheme))
    return len(entries)


def path_for(name, scheme):
    return "sheet-%s-%s.png" % (name, scheme)


HOVER = [
    ("pill", "#save"),
    ("chip", ".chip"),
    ("tile", ".device"),
    ("input", "#screenX"),
    ("latitude", "#geo-lat"),
    ("city", "#geo-place"),
    ("proxy", "#proxy-host"),
    ("proxy route", "#proxy-mode"),
    ("proxy url", "#proxy-url"),
    ("proxy credentials", "#proxy-username"),
    ("import", "#import-pick"),
    ("import apply", "#import-apply"),
    ("stats", "#stats-run"),
    ("diff", "#diff-run"),
    ("delete", "#delete"),
    ("action", "#geo-snap"),
    ("proxy action", "#proxy-apply"),
    ("footer", "#reset-persona"),
]
FOCUS = [
    ("input", "#screenX"),
    ("latitude", "#geo-lat"),
    ("city", "#geo-place"),
    ("select", "#timezone"),
    ("pill", "#save"),
    ("tile", ".device"),
]
ACTIVE = [("pill", "#save"), ("chip", ".chip")]

POPUP_HOVER = [("pill", "#apply"), ("chip", ".chip"), ("select", "#personas"),
               ("action", "#network-link"), ("new identity", "#reshuffle")]
POPUP_FOCUS = [("chip", ".chip"), ("select", "#personas"), ("pill", "#apply")]
POPUP_ACTIVE = [("pill", "#apply"), ("chip", ".chip")]


def main():
    session = launch(PERSONA, url="about:blank", headless=True, extension=str(EXTENSION))
    try:
        if not session.extension_id:
            print("extension did not mount", file=sys.stderr)
            return 2
        global HOVER, FOCUS, ACTIVE
        total = 0
        for scheme in ("light", "dark"):
            HOVER, FOCUS, ACTIVE = POPUP_HOVER, POPUP_FOCUS, POPUP_ACTIVE
            total += capture_surface(session, "popup", "src/popup.html", 360, 620, scheme)
            HOVER, FOCUS, ACTIVE = GLOBAL_HOVER, GLOBAL_FOCUS, GLOBAL_ACTIVE
            total += capture_surface(session, "editor-1280", "src/options.html", 1280, 1400, scheme)
            total += capture_surface(session, "editor-900", "src/options.html", 900, 1400, scheme)
    finally:
        session.close()
    print("%d state crops + %d sheets" % (total, 6))
    return 0


GLOBAL_HOVER = HOVER
GLOBAL_FOCUS = FOCUS
GLOBAL_ACTIVE = ACTIVE

if __name__ == "__main__":
    sys.exit(main())
