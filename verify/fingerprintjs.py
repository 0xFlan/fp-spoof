"""FingerprintJS (v4) harness.

This is the real library, loaded from its CDN, not a local imitation. It needs
a browser and network access, so it only runs from the `live --fpjs` path.

v4 ships as an ES module: the documented usage is
`import('https://openfpcdn.io/fingerprintjs/v4')`, which returns the module
namespace. It does not install a window global, so loading it with a classic
<script> tag succeeds and leaves window.FingerprintJS undefined.

What it demonstrates: two loads in the same profile yield the same visitorId,
and two different profiles yield different ones. A stable ID across profiles
means the profiles are not actually distinguishable; an unstable one means the
render is drifting between visits.
"""
from __future__ import annotations

CDN = "https://openfpcdn.io/fingerprintjs/v4"

READ = r"""async (src) => {
  let lib = window.FingerprintJS;
  if (!lib) {
    lib = await import(src);
  }
  if (!lib || typeof lib.load !== 'function') {
    throw new Error('FingerprintJS module exposes no load()');
  }
  const fp = await lib.load();
  const first = await fp.get();
  const second = await fp.get();
  return {
    visitorId: first.visitorId,
    stableWithinSession: first.visitorId === second.visitorId,
    components: Object.keys(first.components || {}).sort(),
  };
}"""


def read(page, cdn: str = CDN) -> dict:
    return page.evaluate(READ, cdn)
