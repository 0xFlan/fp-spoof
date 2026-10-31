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
python -m api.run mint --platform windows --browser chrome --seed 111 --save
python -m api.run probe --seed 111 --platform windows
python -m api.run list
python -m api.run audit --n 200 --platform windows
python -m api.run live --seed 111 --url https://example.com
python -m api.run live --seed 111 --url https://example.com --fpjs
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

## What CI runs

| Job | What it executes |
|---|---|
| `test` (3.10, 3.12) | `compileall`, the full suite, CLI wiring, and a `probe` / `audit` smoke test |
| `browser` | real Chromium: the two browser tests, an end-to-end probe, and FingerprintJS v4 loaded twice to check the visitorId is stable |

The browser job fails if the browser tests *skip*. A skipped pytest exits 0, so
without that guard the job would go green having started no browser at all —
which is how the `platformKey` bug survived several green runs.

## Independence from the truth set

`data/browsers.json` is the verifier's reference. The generator must not read
it, or the score measures agreement with its own source.
`tests/test_core.py::test_generator_never_reads_truth` enforces this by
scanning the generator sources.

Running `audit` is therefore expected to report divergences, and those
divergences are findings, not bugs. Fix them by deciding which side is wrong;
do not copy truth into `synth/tables.py`.

Two real findings, both now fixed on both sides:

- `deviceMemory` held `16`, `32` and `64` in the tables *and* in the truth set.
  Chrome clamps `navigator.deviceMemory` to 8 GiB and rounds to a power of two,
  so no browser emits those. The 1.5-bit entropy gate is what pushed the tables
  there: a real 4/8 population carries one bit, so inventing larger values was
  the only way to pass. `deviceMemory` is now exempt from that gate.
- Mac core counts were wrong in both directions: the generator omitted 4-core
  Intel machines, and the truth omitted 10-core Apple silicon.

## What is not covered

- Fonts, audio, WebRTC and TLS/JA4 are not modelled.
- Safari and iOS profiles are rendered in **Chromium**, so only Chrome and Edge
  profiles are engine-accurate; `navigator.userAgentData` still reports
  Chromium brands whatever the UA says.
- Safari does not implement `navigator.deviceMemory` at all, so a Safari profile
  that reports one is internally inconsistent. This is not yet special-cased.
- `live --fpjs` needs network access to `openfpcdn.io`. CI exercises it; locally
  it will fail without a network.
- Browser tests are opt-in locally: `FP_SPOOF_BROWSER=1 python -m pytest tests -q`.
