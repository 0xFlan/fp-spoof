"""Read a rendered profile back out of a live page.

diff() is pure, so the comparison logic is testable without a browser; only
observe() needs playwright.
"""

from __future__ import annotations

from synth import tables

PROBE = r"""() => {
  const canvas = document.createElement('canvas');
  let vendor = null;
  let renderer = null;
  try {
    const gl = canvas.getContext('webgl') || canvas.getContext('experimental-webgl');
    if (gl) {
      const ext = gl.getExtension('WEBGL_debug_renderer_info');
      if (ext) {
        vendor = gl.getParameter(ext.UNMASKED_VENDOR_WEBGL);
        renderer = gl.getParameter(ext.UNMASKED_RENDERER_WEBGL);
      }
    }
  } catch (err) {}
  return {
    cores: navigator.hardwareConcurrency,
    memory: navigator.deviceMemory,
    platformKey: navigator.platform,
    languages: Array.from(navigator.languages || []),
    screenX: screen.width,
    screenY: screen.height,
    dpr: window.devicePixelRatio,
    touchPoints: navigator.maxTouchPoints,
    zone: -new Date().getTimezoneOffset() / 60,
    webglVendor: vendor,
    webglRenderer: renderer,
    webdriver: navigator.webdriver,
  };
}"""

EXPECTED_KEYS = (
    "cores",
    "memory",
    "platformKey",
    "languages",
    "screenX",
    "screenY",
    "dpr",
    "touchPoints",
    "zone",
    "webglVendor",
    "webglRenderer",
    "webdriver",
)


def diff(profile, observed, caps=None) -> list:
    """Fields where the live page disagrees with the promise.

    `caps` defaults to the profile's engine capabilities. A field the engine
    cannot expose is expected to be ABSENT, which is a different assertion
    from "present with the right value": a page that still reports
    deviceMemory when the engine has no such property is precisely the shim
    artifact a detector looks for.
    """
    if caps is None:
        caps = tables.BROWSER_CAPS.get(profile.browser, {})

    expected = {
        "cores": profile.hardwareConcurrency,
        "memory": profile.deviceMemory if caps.get("deviceMemory", True) else None,
        "platformKey": profile.platformKey,
        "languages": list(profile.languagesZ),
        "screenX": profile.screenX,
        "screenY": profile.screenY,
        "dpr": float(profile.pixelRatio),
        "touchPoints": profile.touchPoints,
        "zone": profile.zone,
        "webglVendor": profile.wglVendor,
        "webglRenderer": profile.wglRenderer,
        "webdriver": False,
    }

    problems = []
    for key in EXPECTED_KEYS:
        want = expected[key]
        got = observed.get(key)
        if want is None:
            ok = got is None
        elif key == "dpr":
            ok = isinstance(got, (int, float)) and abs(float(got) - want) < 1e-6
        elif key == "languages":
            ok = list(got or []) == want
        else:
            ok = got == want
        if not ok:
            problems.append({"field": key, "expected": want, "observed": got})
    return problems


def observe(page) -> dict:
    return page.evaluate(PROBE)
