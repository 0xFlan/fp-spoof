"""Build the init script that makes a page see the profile.

Two requirements pull against each other: the values must be IDENTICAL on
every visit for one profile (or the fingerprint moves), and they must DIFFER
between profiles (or every profile collapses into one device). Every value
here is derived from the profile alone, so both hold.

Where a value lives matters as much as the value. A real browser exposes
these as inherited getters on Navigator.prototype / Screen.prototype, so an
own property on the instance is a tell even when the number is right.
Properties the engine does not expose are not defined at all.
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

  // Functions whose source should read as native.
  const disguised = [];
  const originalToString = Function.prototype.toString;
  const toString = function toString() {
    if (this === toString || disguised.indexOf(this) !== -1) {
      return 'function ' + (this.name || '') + '() { [native code] }';
    }
    return originalToString.call(this);
  };
  try {
    Object.defineProperty(Function.prototype, 'toString', {
      value: toString, configurable: true, writable: true,
    });
  } catch (err) {}

  const define = (target, name, value) => {
    try {
      Object.defineProperty(target, name, {
        get: () => value, configurable: true, enumerable: true,
      });
      return true;
    } catch (err) { return false; }
  };

  // Prefer the prototype, then clear any own property that would shadow it.
  const inherit = (proto, instance, name, value) => {
    if (proto && define(proto, name, value)) {
      try {
        if (instance && Object.prototype.hasOwnProperty.call(instance, name)) {
          delete instance[name];
        }
      } catch (err) {}
      return;
    }
    if (instance) define(instance, name, value);
  };

  const navigatorProto = window.Navigator && Navigator.prototype;
  inherit(navigatorProto, navigator, 'hardwareConcurrency', P.cores);
  if (P.caps.deviceMemory) {
    inherit(navigatorProto, navigator, 'deviceMemory', P.memory);
  }
  inherit(navigatorProto, navigator, 'platform', P.platformKey);
  inherit(navigatorProto, navigator, 'language', P.languages[0]);
  inherit(navigatorProto, navigator, 'languages', P.languages);
  inherit(navigatorProto, navigator, 'webdriver', false);
  inherit(navigatorProto, navigator, 'maxTouchPoints', P.touchPoints);
  inherit(navigatorProto, navigator, 'pdfViewerEnabled', P.pdf);

  try {
    const makePlugin = (name) => ({
      name, filename: 'internal-pdf-viewer', description: 'Portable Document Format',
    });
    const plugins = P.plugins.map(makePlugin);
    plugins.item = (i) => plugins[i] || null;
    plugins.namedItem = (n) => plugins.find((p) => p.name === n) || null;
    plugins.refresh = () => undefined;
    inherit(navigatorProto, navigator, 'plugins', plugins);
  } catch (err) {}

  const screenProto = window.Screen && Screen.prototype;
  inherit(screenProto, screen, 'width', P.screenX);
  inherit(screenProto, screen, 'height', P.screenY);
  inherit(screenProto, screen, 'availWidth', P.screenX);
  inherit(screenProto, screen, 'availHeight', P.screenY - (P.platform === 'windows' ? 40 : 0));
  inherit(screenProto, screen, 'colorDepth', 24);
  inherit(screenProto, screen, 'pixelDepth', 24);
  inherit(window.Window && Window.prototype, window, 'devicePixelRatio', P.dpr);

  const patchGL = (proto) => {
    if (!proto || !proto.getParameter) return;
    const original = proto.getParameter;
    const patched = function getParameter(parameter) {
      try {
        if (parameter === 0x9245) return P.webglVendor;
        if (parameter === 0x9246) return P.webglRenderer;
        if (parameter === 0x1F01) return P.webglRenderer;
      } catch (err) {}
      return original.apply(this, arguments);
    };
    proto.getParameter = patched;
    disguised.push(patched);
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
      const patched = function getImageData() {
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
      CanvasRenderingContext2D.prototype.getImageData = patched;
      disguised.push(patched);
    }
  } catch (err) {}

  try {
    if (window.HTMLCanvasElement) {
      const original = HTMLCanvasElement.prototype.toDataURL;
      const patched = function toDataURL() {
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
        return original.apply(this, arguments);
      };
      HTMLCanvasElement.prototype.toDataURL = patched;
      disguised.push(patched);
    }
  } catch (err) {}
})();
"""


def init_script(profile) -> str:
    return INIT_SCRIPT.replace(PROFILE_TOKEN, json.dumps(payload(profile)))
