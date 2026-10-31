"""Profile data model + canonical constraints."""
from dataclasses import dataclass, field, asdict
from typing import Any

# Cross-field constraints. Violation => reject at reconcile().
CONSTRAINTS = [
    ("browser","safari",("touchPoints",7),("plugins",["none"])),
    ("platform","windows",("architecture",["amd64"])),
    ("platform","mac",("architecture",["x86_64"])),
    ("platform","ios",("architecture",["arm64"])),
]

@dataclass
class Profile:
    name: str = "pool-default"
    pool: str = "default"
    browser: str = "chrome"
    platform: str = "windows"
    screenX: int = 1920
    screenY: int = 1080
    deviceMemory: int = 8
    hardwareConcurrency: int = 8
    pixelRatio: float = 1.0
    languagesZ: list[str] = field(default_factory=lambda: ["en-US","en"])
    sensors: bool = False
    touchPoints: int = 14
    ua: str = ""
    plugins: tuple[str,...] = ("PDF Viewer","Java")
    pdfViewer: str = ""
    java: str = ""
    platformKey: str = ""
    zString: str = ""

    @property
    def hits(self): return getattr(self,"_hits",0)
    @hits.setter
    def hits(self,v): self._hits=v

    def to_dict(self): return asdict(self)
