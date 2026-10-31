"""FingerprintJS (v4) harness.

This is the real library, loaded from its CDN, not a local imitation. It needs
a browser and network access, so it only runs from the `live --fpjs` path.

What it demonstrates: two loads in the same profile yield the same visitorId,
and two different profiles yield different ones. A stable ID across profiles
means the profiles are not actually distinguishable; an unstable one means the
render is drifting between visits.
"""
from __future__ import annotations

CDN = "https://openfpcdn.io/fingerprintjs/v4"

READ = r"""async (src) => {
  if (!window.FingerprintJS) {
    await new Promise((resolve, reject) => {
      const script = document.createElement('script');
      script.src = src;
      script.onload = resolve;
      script.onerror = () => reject(new Error('failed to load ' + src));
      document.head.appendChild(script);
    });
  }
  const fp = await window.FingerprintJS.load();
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
