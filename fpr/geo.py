"""Location data.

Coordinates belong to a fingerprint as much as a user agent does: sites ask
``navigator.geolocation`` for a position, and a coordinate that disagrees with
the reported timezone is a contradiction no real device produces. The table in
``data/geo.json`` maps every catalog timezone to a city, so a persona carries
location data that is consistent by construction.
"""

from __future__ import annotations

import json
import math
import os
from functools import lru_cache
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from fpr import catalog

DEFAULT_TOLERANCE_KM = 250.0


class GeoError(RuntimeError):
    """Raised when the location table is missing or malformed."""


def data_path() -> Path:
    override = os.environ.get("FPSPOOF_GEO")
    return Path(override).expanduser() if override else catalog.BASE / "data" / "geo.json"


@lru_cache(maxsize=1)
def load() -> Dict[str, Any]:
    path = data_path()
    try:
        with open(path, encoding="utf-8") as fh:
            data = json.load(fh)
    except OSError as exc:
        raise GeoError("cannot read location table at %s: %s" % (path, exc)) from exc
    except ValueError as exc:
        raise GeoError("location table at %s is not valid JSON: %s" % (path, exc)) from exc
    if not isinstance(data.get("cities"), dict) or not data["cities"]:
        raise GeoError("location table at %s has no cities" % path)
    return data


def reload() -> Dict[str, Any]:
    load.cache_clear()
    return load()


def cities() -> Dict[str, Dict[str, Any]]:
    return load()["cities"]


def city(timezone: str) -> Optional[Dict[str, Any]]:
    return cities().get(str(timezone or ""))


def distance_km(a: Tuple[float, float], b: Tuple[float, float]) -> float:
    """Great-circle distance between two ``(latitude, longitude)`` pairs."""
    lat1, lon1 = math.radians(a[0]), math.radians(a[1])
    lat2, lon2 = math.radians(b[0]), math.radians(b[1])
    dlat, dlon = lat2 - lat1, lon2 - lon1
    h = math.sin(dlat / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon / 2) ** 2
    return round(2 * 6371.0088 * math.asin(min(1.0, math.sqrt(h))), 1)


def nearest(latitude: float, longitude: float) -> Optional[Tuple[str, Dict[str, Any], float]]:
    """``(timezone, city, distance_km)`` for the closest catalog city."""
    best: Optional[Tuple[str, Dict[str, Any], float]] = None
    for zone, entry in cities().items():
        try:
            point = (float(entry["latitude"]), float(entry["longitude"]))
        except (KeyError, TypeError, ValueError):
            continue
        span = distance_km((float(latitude), float(longitude)), point)
        if best is None or span < best[2]:
            best = (zone, entry, span)
    return best


def geo_for(timezone: str) -> Dict[str, Any]:
    """Location payload for a persona in ``timezone``."""
    entry = city(timezone)
    if entry is None:
        return {"latitude": 0.0, "longitude": 0.0, "accuracy": 1000.0,
                "city": "unknown", "country": "ZZ"}
    return {
        "latitude": float(entry["latitude"]),
        "longitude": float(entry["longitude"]),
        "accuracy": float(entry.get("accuracy", 50.0)),
        "city": str(entry.get("city", "")),
        "country": str(entry.get("country", "")),
    }


def check(persona: Dict[str, Any], tolerance_km: float = DEFAULT_TOLERANCE_KM) -> List[str]:
    """Consistency codes for a persona's location payload (empty means fine)."""
    payload = (persona or {}).get("geo")
    if not payload:
        return []
    if not isinstance(payload, dict):
        return ["geo-invalid"]
    try:
        latitude = float(payload.get("latitude"))
        longitude = float(payload.get("longitude"))
        accuracy = float(payload.get("accuracy", 50.0))
    except (TypeError, ValueError):
        return ["geo-invalid"]
    if not (-90.0 <= latitude <= 90.0) or not (-180.0 <= longitude <= 180.0):
        return ["geo-out-of-range"]
    if accuracy <= 0:
        return ["geo-invalid"]
    entry = city(str((persona or {}).get("timezone") or ""))
    if entry is None:
        return []
    span = distance_km((latitude, longitude),
                       (float(entry["latitude"]), float(entry["longitude"])))
    return ["geo-timezone-mismatch"] if span > tolerance_km else []
