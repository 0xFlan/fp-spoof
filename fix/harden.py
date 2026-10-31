"""Stable-per-profile GPU and canvas hardening.

Requirement: every value here is IDENTICAL across visits for one profile and
DIFFERENT between profiles. A global constant leaks (it collapses the whole
pool to one device); a value re-randomised per visit leaks harder (the same
visitor changes canvas hash on refresh).

Vendor, renderer and adapter are sampled as a matched triple so they cannot
contradict each other.
"""
from __future__ import annotations

APPLE_GPU = (
    ("Apple Inc.", "Apple GPU", "Apple M1"),
    ("Apple Inc.", "Apple GPU", "Apple M2"),
    ("Apple Inc.", "Apple GPU", "Apple M3"),
)

DESKTOP_GPU = (
    (
        "Google Inc. (Intel)",
        "ANGLE (Intel, Intel(R) UHD Graphics 630 Direct3D11 vs_5_0 ps_5_0, D3D11)",
        "Intel(R) UHD Graphics 630",
    ),
    (
        "Google Inc. (Intel)",
        "ANGLE (Intel, Intel(R) Iris(R) Xe Graphics Direct3D11 vs_5_0 ps_5_0, D3D11)",
        "Intel(R) Iris(R) Xe Graphics",
    ),
    (
        "Google Inc. (NVIDIA)",
        "ANGLE (NVIDIA, NVIDIA GeForce RTX 3060 Direct3D11 vs_5_0 ps_5_0, D3D11)",
        "NVIDIA GeForce RTX 3060",
    ),
    (
        "Google Inc. (AMD)",
        "ANGLE (AMD, AMD Radeon RX 6600 Direct3D11 vs_5_0 ps_5_0, D3D11)",
        "AMD Radeon RX 6600",
    ),
)

GPU_BY_PLATFORM = {
    "mac": APPLE_GPU,
    "ios": APPLE_GPU,
}


def gpu_strings(rng, platform="windows"):
    """Return a matched {vendor, renderer, adapter} triple for one profile."""
    pool = GPU_BY_PLATFORM.get(platform, DESKTOP_GPU)
    vendor, renderer, adapter = rng.choice(pool)
    return {"vendor": vendor, "renderer": renderer, "adapter": adapter}


def canvas_noise(rng, pixels=8):
    """Per-profile canvas perturbation. Stable for a fixed rng seed."""
    return tuple(rng.randint(-2, 2) for _ in range(pixels))
