"""Look for the shim rather than the values it produces.

A spoofed value can be correct and still detectable. A detector does not need
to know the truth to see the machinery:

    Object.getOwnPropertyDescriptor(navigator, 'hardwareConcurrency')
    // null in a real browser; a getter means someone patched the instance

    Function.prototype.toString.call(getParameter)
    // 'function () { [native code] }' in a real browser, readable JS otherwise

Every finding here is a fact about how the value was installed, not about
what it claims, so this probe stays useful when the tables change.
"""

from __future__ import annotations

PROBE = r"""() => {
  const findings = [];

  const own = (target, name, label) => {
    try {
      if (Object.getOwnPropertyDescriptor(target, name)) {
        findings.push(label + ':' + name);
      }
    } catch (err) {}
  };

  const navigatorProps = [
    'hardwareConcurrency', 'deviceMemory', 'platform', 'language',
    'languages', 'webdriver', 'maxTouchPoints', 'plugins',
    'pdfViewerEnabled',
  ];
  for (const name of navigatorProps) own(navigator, name, 'own-navigator');

  for (const name of ['width', 'height', 'availWidth', 'availHeight', 'colorDepth', 'pixelDepth']) {
    own(screen, name, 'own-screen');
  }
  own(window, 'devicePixelRatio', 'own-window');

  const isNative = (fn) => {
    try {
      return Function.prototype.toString.call(fn).indexOf('[native code]') !== -1;
    } catch (err) {
      return true;
    }
  };

  const patched = [
    ['canvas.getImageData', () => window.CanvasRenderingContext2D && CanvasRenderingContext2D.prototype.getImageData],
    ['canvas.toDataURL', () => window.HTMLCanvasElement && HTMLCanvasElement.prototype.toDataURL],
    ['webgl.getParameter', () => window.WebGLRenderingContext && WebGLRenderingContext.prototype.getParameter],
    ['webgl2.getParameter', () => window.WebGL2RenderingContext && WebGL2RenderingContext.prototype.getParameter],
  ];
  for (const [label, get] of patched) {
    try {
      const fn = get();
      if (fn && !isNative(fn)) findings.push('readable-source:' + label);
    } catch (err) {}
  }

  // The disguise itself must not stand out.
  try {
    const toString = Function.prototype.toString;
    if (!isNative(toString)) findings.push('readable-source:Function.prototype.toString');
    if (toString.call(toString).indexOf('[native code]') === -1) {
      findings.push('readable-source:toString-self');
    }
  } catch (err) {
    findings.push('toString-unavailable');
  }

  return findings;
}"""


def findings(page) -> list:
    """Shim artifacts the page can see. Empty means nothing obvious sticks out."""
    return page.evaluate(PROBE)
