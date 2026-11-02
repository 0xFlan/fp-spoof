"""Profile data model and the canonical cross-field constraints.

Constraints live here and nowhere else.  ``CONSTRAINTS`` is *derived* from the
catalog at import time, which is what the previous build got wrong: it kept a
hand-written rule table in this module and a second, contradictory rule table
in ``fix/reconcile.py``, so "valid" meant two different things depending on who
you asked.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Optional, Tuple

from fpr import catalog

# Fields whose value is fully determined by the platform, not chosen.
PLATFORM_KEY = {
    "windows": "Win32",
    "mac": "MacIntel",
    "linux": "Linux x86_64",
    "ios": "iPhone",
}

# 0 on every desktop, a real touch count on phones.
TOUCH_POINTS = {"windows": 0, "mac": 0, "linux": 0, "ios": 5}


def constraints() -> Dict[str, Dict[str, Any]]:
    """Browser rules, derived from the catalog."""
    out: Dict[str, Dict[str, Any]] = {}
    for name, spec in catalog.browsers().items():
        out[name] = {
            "platforms": list(spec["platforms"]),
            "sensors": bool(spec["sensors"]),
            "plugins": tuple(spec["plugins"]),
            "supportsDeviceMemory": bool(spec["supportsDeviceMemory"]),
            "vendor": spec["vendor"],
            "browserToken": spec["browserToken"],
        }
    return out


# Kept as a module-level name for backwards compatibility with the old API.
CONSTRAINTS = constraints()


def constraint(browser: str) -> Dict[str, Any]:
    try:
        return CONSTRAINTS[browser]
    except KeyError:
        raise catalog.CatalogError(
            "unknown browser %r; known browsers: %s" % (browser, ", ".join(sorted(CONSTRAINTS)))
        ) from None


@dataclass
class Profile:
    """One browser identity.

    A profile is only meaningful if every field is plausible *together*; see
    :func:`fix.reconcile.reconcile` for the consistency checks.
    """

    name: str = "pool-default"
    pool: str = "default"
    browser: str = "chrome"
    platform: str = "windows"
    version: str = ""
    screenX: int = 1920
    screenY: int = 1080
    availX: int = 1920
    availY: int = 1040
    deviceMemory: Optional[int] = 8
    hardwareConcurrency: int = 8
    pixelRatio: float = 1.0
    maxTouchPoints: int = 0
    # Legacy alias, mirrors maxTouchPoints.
    touchPoints: int = 0
    languagesZ: List[str] = field(default_factory=lambda: ["en-US", "en"])
    timezone: str = "America/New_York"
    sensors: bool = False
    ua: str = ""
    platformKey: str = "Win32"
    architecture: str = "x86_64"
    vendor: str = "Google Inc."
    webglVendor: str = ""
    webglRenderer: str = ""
    plugins: Tuple[str, ...] = ()
    pdfViewer: str = ""
    java: str = ""
    zone: int = 10
    colorDepth: int = 24
    userAgentData: Dict[str, Any] = field(default_factory=dict)
    seed: int = 0

    def to_dict(self) -> Dict[str, Any]:
        data = asdict(self)
        data["plugins"] = list(self.plugins)
        return data

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Profile":
        known = {f for f in cls.__dataclass_fields__}  # type: ignore[attr-defined]
        kwargs = {k: v for k, v in data.items() if k in known}
        if "plugins" in kwargs:
            kwargs["plugins"] = tuple(kwargs["plugins"] or ())
        return cls(**kwargs)

    @property
    def hits(self) -> int:
        return getattr(self, "_hits", 0)

    @hits.setter
    def hits(self, value: int) -> None:
        self._hits = int(value)

    def __post_init__(self) -> None:
        # ``touchPoints`` was the name the old reconciler read; keep the two in
        # sync so serialized profiles stay usable either way.
        if self.touchPoints != self.maxTouchPoints:
            if self.maxTouchPoints:
                self.touchPoints = self.maxTouchPoints
            else:
                self.maxTouchPoints = self.touchPoints
        if self.plugins and not isinstance(self.plugins, tuple):
            self.plugins = tuple(self.plugins)
