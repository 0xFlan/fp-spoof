"""Tunables. Single source of truth: no other module hardcodes these values."""

DEFAULT_SEED = 111
DEFAULT_POOL = "default"

# Population gates (fpr/entropy.py). These describe a POOL of profiles, never
# a single profile; entropy is undefined for one sample.
MIN_FIELD_BITS = 1.5
MAX_KL_BITS = 0.75

# Single-profile gate (verify/score.py).
MIN_CONSISTENCY = 0.75
