"""Population statistics.

Entropy belongs to a DISTRIBUTION, not to a profile: it is undefined for a
single sample. These functions therefore take a population (many minted
profiles) or one field's value list. The single-profile case is covered by
fpr/stability.py.

The previous implementation returned -1.0 for every input (it summed a
probability vector without the log) and scored the generator against the same
table it sampled from, so it could never fail.
"""
from __future__ import annotations

import math
from collections import Counter

from constants import MAX_KL_BITS, MIN_FIELD_BITS

DEFAULT_FIELDS = ("deviceMemory", "hardwareConcurrency", "pixelRatio", "zone")


def empirical(values) -> dict:
    """Frequency table. Duplicate entries in a list are intentional weight."""
    values = list(values)
    if not values:
        return {}
    counts = Counter(values)
    return {value: count / len(values) for value, count in counts.items()}


def field_bits(values) -> float:
    """Shannon entropy in bits for one field across a population."""
    frequencies = empirical(values)
    return -sum(p * math.log2(p) for p in frequencies.values() if p > 0)


def kl_bits(sample, reference, alpha: float = 0.5) -> float:
    """KL(sample || reference) in bits, Laplace-smoothed over the union support.

    alpha > 0 keeps the result finite when the sample emits a value the
    reference never contains; support_gaps() reports that case explicitly.
    """
    sample = list(sample)
    if not sample:
        return float("inf")

    counts = Counter(sample)
    n = len(sample)
    support = sorted(set(counts) | set(reference), key=str)
    k = len(support)

    total = 0.0
    for value in support:
        if alpha:
            p = (counts.get(value, 0) + alpha) / (n + alpha * k)
            q = (reference.get(value, 0.0) + alpha) / (1.0 + alpha * k)
        else:
            p = counts.get(value, 0) / n
            q = reference.get(value, 0.0)
            if q == 0.0:
                return float("inf")
            if p == 0.0:
                continue
        total += p * math.log2(p / q)
    return total


def support_gaps(sample, reference) -> dict:
    """Values we emit that truth never has, and truth values we never emit."""
    seen = set(sample)
    known = set(reference)
    return {
        "unknown": sorted(map(str, seen - known)),
        "missing": sorted(map(str, known - seen)),
    }


def population_report(profiles, truth=None, fields=DEFAULT_FIELDS) -> dict:
    truth = truth or {}
    report = {}
    for field in fields:
        values = [getattr(profile, field) for profile in profiles]
        entry = {"n": len(values), "bits": round(field_bits(values), 3)}
        reference = truth.get(field)
        if reference:
            entry["kl"] = round(kl_bits(values, reference), 3)
            gaps = support_gaps(values, reference)
            if gaps["unknown"] or gaps["missing"]:
                entry["support"] = gaps
        report[field] = entry
    return report


def passes(report, min_bits=MIN_FIELD_BITS, max_kl=MAX_KL_BITS):
    failures = []
    for field, entry in report.items():
        if entry["bits"] < min_bits:
            failures.append(f"{field}: bits {entry['bits']} < {min_bits}")
        if "kl" in entry and entry["kl"] > max_kl:
            failures.append(f"{field}: kl {entry['kl']} > {max_kl}")
        unknown = entry.get("support", {}).get("unknown")
        if unknown:
            failures.append(f"{field}: emits values truth never has: {unknown}")
    return (not failures, failures)
