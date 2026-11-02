"""Catalog loading.

``data/browsers.json`` is the single source of truth for what a plausible
device looks like.  Everything else (generation, validation, entropy) derives
from it so the rules cannot drift apart the way they did in the old build.

The file is read once per process and cached; lookups are plain dict access.
"""

from __future__ import annotations

import json
import os
from functools import lru_cache
from pathlib import Path
from typing import Any, Dict, List, Tuple

BASE = Path(__file__).resolve().parents[1]
DEFAULT_DATA = BASE / "data" / "browsers.json"


class CatalogError(RuntimeError):
    """Raised when the persona catalog is missing or malformed."""


def data_path() -> Path:
    """Resolve the catalog path, honouring ``FPSPOOF_DATA``."""
    override = os.environ.get("FPSPOOF_DATA")
    if override:
        return Path(override).expanduser()
    return DEFAULT_DATA


@lru_cache(maxsize=1)
def load() -> Dict[str, Any]:
    path = data_path()
    try:
        with open(path, encoding="utf-8") as fh:
            data = json.load(fh)
    except OSError as exc:
        raise CatalogError("cannot read persona catalog at %s: %s" % (path, exc)) from exc
    except ValueError as exc:
        raise CatalogError("persona catalog at %s is not valid JSON: %s" % (path, exc)) from exc

    missing = [key for key in ("browsers", "os", "screens", "gpus", "locale") if key not in data]
    if missing:
        raise CatalogError(
            "persona catalog at %s is missing sections: %s" % (path, ", ".join(missing))
        )
    return data


def reload() -> Dict[str, Any]:
    """Drop the cache and re-read the catalog (used by tests)."""
    load.cache_clear()
    return load()


def browsers() -> Dict[str, Any]:
    return load()["browsers"]


def os_table() -> Dict[str, Any]:
    return load()["os"]


def screens() -> Dict[str, List[List[float]]]:
    return load()["screens"]


def gpus() -> Dict[str, List[Dict[str, str]]]:
    return load()["gpus"]


def locale() -> Dict[str, Any]:
    return load()["locale"]


def browser(name: str) -> Dict[str, Any]:
    table = browsers()
    if name not in table:
        raise CatalogError(
            "unknown browser %r; known browsers: %s" % (name, ", ".join(sorted(table)))
        )
    return table[name]


def platform(name: str) -> Dict[str, Any]:
    table = os_table()
    if name not in table:
        raise CatalogError(
            "unknown platform %r; known platforms: %s" % (name, ", ".join(sorted(table)))
        )
    return table[name]


def platforms_for(name: str) -> List[str]:
    return list(browser(name)["platforms"])


def combos() -> List[Tuple[str, str]]:
    """Every supported ``(browser, platform)`` pair, catalog order."""
    out: List[Tuple[str, str]] = []
    for name, spec in browsers().items():
        for plat in spec["platforms"]:
            out.append((name, plat))
    return out


def gpus_for(platform_name: str, architecture: str) -> List[Dict[str, str]]:
    """GPUs plausible for a platform, preferring the matching architecture."""
    table = gpus().get(platform_name, [])
    matching = [gpu for gpu in table if gpu.get("arch") in (None, architecture)]
    return matching or table


def screens_for(platform_name: str) -> List[List[float]]:
    kind = platform(platform_name).get("screen", "desktop")
    return screens().get(kind) or screens()["desktop"]


# Backwards-compatible alias for the old module-level ``CATA`` constant.
def cata() -> Dict[str, Any]:
    return load()
