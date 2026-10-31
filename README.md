# fp-spoof

Mint internally consistent browser fingerprints, render them in a real headless
browser, and score the result against the values that were promised.

## Install

```bash
pip install pytest
# only for the browser layer:
pip install playwright && playwright install chromium
```

## Use

```bash
python -m api.run mint  --platform windows --browser chrome --seed 111 --save
python -m api.run probe --seed 111 --platform windows
python -m api.run list
python -m api.run audit --n 200 --platform windows
python -m api.run live  --seed 111 --url https://example.com
python -m api.run live  --seed 111 --url https://example.com --fpjs
```

Exit codes: `0` accepted, `1` rejected, `2` usage error.

## How it fits together

| Path | Role |
|---|---|
| `synth/mint.py` | `mint(seed)` is a pure function; the seed reproduces the profile exactly |
| `synth/tables.py` | generation distributions, written without reading the truth set |
| `fix/reconcile.py` | cross-field validator; returns error codes and never raises |
| `fpr/entropy.py` | Shannon entropy and KL divergence over a population |
| `fpr/stability.py` | `digest()` over the observable fields |
| `verify/truth.py` | the only reader of `data/browsers.json` |
| `render/` | Playwright context, client hints, init script |
| `verify/browser_probe.py` | reads a live page back and diffs it against the profile |
| `models/store.py` | SQLite, one row per `(name, pool)` |
| `api/run.py` | CLI |

## The two properties being tested

**Stable.** `digest(mint(s)) == digest(mint(s))`, and the same seed renders the
same values on every visit. A value randomised per visit is not a fingerprint,
it is noise that changes on refresh.

**Varied.** `digest(mint(a)) != digest(mint(b))`. A constant GPU string for
every profile collapses the whole pool into one device.

Entropy is a property of the population, not of a profile, so `audit` scores
many minted profiles and `probe` scores one.

## Independence from the truth set

`data/browsers.json` is the verifier's reference. The generator must not read
it, or the score measures agreement with its own source.
`tests/test_core.py::test_generator_never_reads_truth` enforces this by
scanning the generator sources.

Running `audit` is therefore expected to report divergences the first time,
and those divergences are real findings, not bugs. Fix them by deciding which
side is wrong; do not copy truth into `synth/tables.py`.

## What is not covered

- Fonts, audio, WebRTC and TLS/JA4 are not modelled.
- `live --fpjs` needs network access to `openfpcdn.io`.
- Browser tests are opt-in: `FP_SPOOF_BROWSER=1 python -m pytest tests -q`.
