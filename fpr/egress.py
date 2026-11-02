"""Observed egress, checked against a persona.

Run only when the user asks: the check contacts a third-party IP-echo service.
It answers the one question a fingerprint cannot: where does traffic actually
leave from, and does that match the city the persona claims?
"""

from __future__ import annotations

import json
import math
import urllib.request
from typing import Any, Callable, Dict, Optional

ENDPOINT = "https://ipinfo.io/json"
EARTH_KM = 6371.0


class EgressError(RuntimeError):
    """Raised when the egress check cannot be completed."""


def fetch(url: str = ENDPOINT, timeout: float = 6.0) -> Dict[str, Any]:
    request = urllib.request.Request(
        url,
        headers={"Accept": "application/json", "User-Agent": "fp-spoof-egress/1"},
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except (OSError, ValueError) as exc:
        raise EgressError("egress check failed: %s" % exc)
    if not isinstance(payload, dict) or not payload.get("ip"):
        raise EgressError("egress check returned no IP")
    return payload


def distance_km(lat_a: float, lon_a: float, lat_b: float, lon_b: float) -> float:
    phi_a, phi_b = math.radians(lat_a), math.radians(lat_b)
    d_phi = math.radians(lat_b - lat_a)
    d_lambda = math.radians(lon_b - lon_a)
    h = math.sin(d_phi / 2) ** 2 + math.cos(phi_a) * math.cos(phi_b) * math.sin(d_lambda / 2) ** 2
    return 2 * EARTH_KM * math.asin(math.sqrt(h))


def compare(observed: Dict[str, Any], persona: Optional[Dict[str, Any]],
            fetch_json: Optional[Callable[..., Dict[str, Any]]] = None,
            endpoint: str = ENDPOINT) -> Dict[str, Any]:
    payload = observed if observed else (fetch_json or fetch)(endpoint)
    notes = []
    geo = (persona or {}).get("geo") or {}
    expected = {
        "city": geo.get("city"),
        "timezone": geo.get("timezone") or (persona or {}).get("timezone"),
        "lat": geo.get("lat"),
        "lon": geo.get("lon"),
    }
    observed_loc = str(payload.get("loc") or "")
    distance = None
    if observed_loc and expected["lat"] is not None and expected["lon"] is not None:
        try:
            lat_s, lon_s = observed_loc.split(",")
            distance = round(distance_km(float(expected["lat"]), float(expected["lon"]),
                                         float(lat_s), float(lon_s)))
        except (ValueError, TypeError):
            distance = None
    if distance is not None and distance > 300:
        notes.append(
            "observed egress is %d km from %s \u2014 this is not the persona's city"
            % (distance, expected["city"] or "the persona's city")
        )
    if persona is not None and not (persona or {}).get("proxy") and distance is None:
        notes.append("no proxy on this persona: the observed IP is the real one")
    return {
        "observed": {
            "ip": payload.get("ip"),
            "city": payload.get("city"),
            "region": payload.get("region"),
            "country": payload.get("country"),
            "org": payload.get("org"),
            "loc": observed_loc or None,
        },
        "persona": expected,
        "distance_km": distance,
        "notes": notes,
    }
