"""Build the init script that makes a page see the profile.

Two requirements pull against each other: the values must be IDENTICAL on
every visit for one profile (or the fingerprint moves), and they must DIFFER
between profiles (or every profile collapses into one device). Every value
here is derived from the profile alone, so both hold.

Properties the engine does not expose are not defined at all. Defining one
is a contradiction the verifier catches, and the fix belongs here rather
than in a special case per browser.
"""

from __future__ import annotations

import json

from render.timezones import timezone_for
from synth import tables

PROFILE_TOKEN = "__FP_SPOOF_PROFILE__"


def payload(profile) -> dict:
    """What the page should observe.

    Keys match verify/browser_probe.PROBE exactly, so the same dict can be
    diffed against a live observation without translation.
    """
    return {
        "cores": profile.hardwareConcurrency,
        "memory": profile.deviceMemory,
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
        "plugins": list(profile.plugins),
        "pdf": bool(profile.pdfViewer),
        "canvasSalt": profile.canvasSalt,
        "timezone": timezone_for(profile),
        "browser": profile.browser,
        "platform": profile.platform,
        "caps": dict(tables.BROWSER_CAPS.get(profile.browser, {})),
    }


INIT_SCRIPT = r"""
(() => {
  const P = __FP_SPOOF_PROFILE__;

  const define = (target, name, value) => {
    try {
      Object.defineProperty(target, name, {
        get: () => value, configurable: true, enumerable: true,
      });
    } catch (err) { /* host object is frozen; nothing to do */ }
  };

  define(navigator, 'hardwareConcurrency', P.cores);
  if (P.caps.deviceMemory) {
    define(navigator, 'deviceMemory', P.memory);
  }
  define(navigator, 'platform', P.platformKey);
  define(navigator, 'language', P.languages[0]);
  define(navigator, 'languages', P.languages);
  define(navigator, 'webdriver', false);
  define(navigator, 'maxTouchPoints', P.touchPoints);
  define(navigator, 'pdfViewerEnabled', P.pdf);

  try {
    const makePlugin = (name) => ({
      name, filename: 'internal-pdf-viewer', description: 'Portable Document Format',
    });
    const plugins = P.plugins.map(makePlugin);
    plugins.item = (i) => plugins[i] || null;
    plugins.namedItem = (n) => plugins.find((p) => p.name === n) || null;
    plugins.refresh = () => undefined;
    define(navigator, 'plugins', plugins);
  } catch (err) {}

  define(window, 'devicePixelRatio', P.dpr);
  define(screen, 'width', P.screenX);
  define(screen, 'height', P.screenY);
  define(screen, 'availWidth', P.screenX);
  define(screen, 'availHeight', P.screenY - (P.platform === 'windows' ? 40 : 0));
  define(screen, 'colorDepth', 24);
  define(screen, 'pixelDepth', 24);

  const patchGL = (proto) => {
    if (!proto || !proto.getParameter) return;
    const original = proto.getParameter;
    proto.getParameter = function (parameter) {
      try {
        if (parameter === 0x9245) return P.webglVendor;
        if (parameter === 0x9246) return P.webglRenderer;
        if (parameter === 0x1F01) return P.webglRenderer;
      } catch (err) {}
      return original.apply(this, arguments);
    };
  };
  try { patchGL(window.WebGLRenderingContext && WebGLRenderingContext.prototype); } catch (err) {}
  try { patchGL(window.WebGL2RenderingContext && WebGL2RenderingContext.prototype); } catch (err) {}

  const seed = (P.canvasSalt >>> 0) || 1;
  const step = (x) => {
    x ^= x << 13; x >>>= 0;
    x ^= x >>> 17;
    x ^= x << 5;
    return x >>> 0;
  };

  try {
    if (window.CanvasRenderingContext2D) {
      const original = CanvasRenderingContext2D.prototype.getImageData;
      CanvasRenderingContext2D.prototype.getImageData = function () {
        const image = original.apply(this, arguments);
        const data = image.data;
        const pixels = Math.floor(data.length / 4);
        if (!pixels) return image;
        let local = seed;
        const touches = Math.min(16, pixels);
        for (let i = 0; i < touches; i += 1) {
          local = step(local);
          const index = (local % pixels) * 4;
          data[index] = (data[index] + (local % 5) - 2) & 0xff;
        }
        return image;
      };
    }
  } catch (err) {}

  try {
    if (window.HTMLCanvasElement) {
      const toDataURL = HTMLCanvasElement.prototype.toDataURL;
      HTMLCanvasElement.prototype.toDataURL = function () {
        try {
          const ctx = this.getContext('2d');
          if (ctx && this.width && this.height) {
            const x = seed % this.width;
            const y = (seed >>> 8) % this.height;
            const stamp = ctx.getImageData(x, y, 1, 1);
            stamp.data[0] = (stamp.data[0] + (seed % 3) + 1) & 0xff;
            ctx.putImageData(stamp, x, y);
          }
        } catch (err) {}
        return toDataURL.apply(this, arguments);
      };
    }
  } catch (err) {}
})();
"""


def init_script(profile) -> str:
    return INIT_SCRIPT.replace(PROFILE_TOKEN, json.dumps(payload(profile)))
