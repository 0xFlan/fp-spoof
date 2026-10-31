"""Playwright driver.

A persistent context per profile means cookies, localStorage and IndexedDB
survive a restart the way they do for a real visitor: the profile is not just
what the page reads on first load.

Playwright is optional. Importing this module without it is fine; only
session() refuses.
"""
from __future__ import annotations

import contextlib
import os
from pathlib import Path

from render.headers import headers
from render.inject import init_script
from render.timezones import timezone_for

try:
    from playwright.sync_api import sync_playwright
except ImportError:  # pragma: no cover - environment dependent
    sync_playwright = None

ROOT = Path(__file__).resolve().parents[1]
LAUNCH_ARGS = ["--disable-blink-features=AutomationControlled"]


def available() -> bool:
    return sync_playwright is not None

def profiles_root(root=None) -> Path:
    if root:
        return Path(root)
    return Path(os.environ.get("FP_SPOOF_PROFILE_DIR", str(ROOT / "var" / "profiles")))


@contextlib.contextmanager
def session(profile, headless=True, root=None):
    if not available():  # pragma: no cover - environment dependent
        raise RuntimeError(
            "playwright is not installed; run: pip install playwright && playwright install chromium"
        )

    directory = profiles_root(root) / profile.name
    directory.mkdir(parents=True, exist_ok=True)

    with sync_playwright() as playwright:
        context = playwright.chromium.launch_persistent_context(
            user_data_dir=str(directory),
            headless=headless,
            user_agent=profile.ua,
            viewport={"width": profile.screenX, "height": profile.screenY},
            device_scale_factor=float(profile.pixelRatio),
            locale=profile.languagesZ[0],
            timezone_id=timezone_for(profile),
            has_touch=profile.touchPoints > 0,
            extra_http_headers=headers(profile),
            args=LAUNCH_ARGS,
        )
        try:
            context.add_init_script(script=init_script(profile))
            yield context
        finally:
            context.close()
