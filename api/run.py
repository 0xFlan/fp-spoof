"""fp-spoof CLI.

python -m api.run mint --platform windows --browser chrome --seed 111 --save
python -m api.run probe --seed 111 --platform windows
python -m api.run list [--pool default]
python -m api.run use --name profile-chrome-windows-111 [--pool default]
python -m api.run audit --n 200 --platform windows
python -m api.run live --seed 111 --url https://example.com [--headed] [--fpjs]

Exit codes: 0 accepted, 1 rejected, 2 usage error.
"""

from __future__ import annotations

import argparse
import json
import sys

from constants import DEFAULT_POOL, DEFAULT_SEED
from fpr import entropy
from fpr.stability import digest
from fix.reconcile import reconcile
from models import store
from synth import tables
from synth.mint import MintError, mint
from verify import truth
from verify.score import score


def _resolve_browser(platform, browser):
    allowed = tables.ALLOWED[platform]
    if browser is None:
        return allowed[0]
    if browser not in allowed:
        raise MintError(
            f"{browser!r} cannot run on {platform!r}; allowed: {', '.join(allowed)}"
        )
    return browser


def cmd_mint(args):
    profile = mint(args.seed, _resolve_browser(args.platform, args.browser),
                   args.platform, args.pool, name=args.name)
    ok, result = score(profile)
    print(json.dumps({"profile": profile.to_dict(), "accepted": ok, **result},
                     indent=2, default=str))
    if ok and args.save:
        store.save(profile, consistency=result["consistency"])
        print(f"saved {profile.name} -> {store.dbpath()}", file=sys.stderr)
    return 0 if ok else 1


def cmd_probe(args):
    profile = mint(args.seed, _resolve_browser(args.platform, args.browser),
                   args.platform, args.pool)
    ok, result = score(profile)
    print(json.dumps({"accepted": ok, **result}, indent=2, default=str))
    return 0 if ok else 1


def cmd_list(args):
    rows = store.list_profiles(args.pool)
    if not rows:
        print("no profiles")
        return 0
    for row in rows:
        print("\t".join(str(value) for value in row))
    return 0


def cmd_use(args):
    """Record that a stored profile was loaded.

    The only writer of the hits column. A missing name is a rejection rather
    than a silent no-op, so a caller cannot believe it reused a profile that
    was never saved.
    """
    updated = store.record_hit(args.name, args.pool)
    if not updated:
        print(
            f"no profile named {args.name!r} in pool {args.pool!r}",
            file=sys.stderr,
        )
        return 1
    row = store.get(args.name, args.pool)
    print(json.dumps({"name": row[0], "pool": row[1], "hits": row[7]}, indent=2))
    return 0


def cmd_audit(args):
    allowed = tables.ALLOWED[args.platform]
    profiles = [
        mint(args.seed + offset, allowed[offset % len(allowed)], args.platform, args.pool)
        for offset in range(args.n)
    ]
    rejected = [profile.name for profile in profiles if reconcile(profile)]
    report = entropy.population_report(profiles, truth.distributions(args.platform))
    ok, failures = entropy.passes(report)
    print(json.dumps({
        "platform": args.platform,
        "n": len(profiles),
        "rejected": len(rejected),
        # Distinct FINGERPRINTS, not distinct wglRenderer values: every Apple
        # device reports "Apple GPU", so counting renderers made a healthy
        # population of 50 mac profiles look like a single device.
        "distinctFingerprints": len({digest(profile) for profile in profiles}),
        "report": report,
        "passes": ok,
        "failures": failures,
    }, indent=2, default=str))
    return 0 if ok and not rejected else 1


def cmd_live(args):
    """Render the profile in a real browser and read it back."""
    from render.driver import session
    from verify.browser_probe import PROBE, diff

    profile = mint(args.seed, _resolve_browser(args.platform, args.browser),
                   args.platform, args.pool)
    with session(profile, headless=not args.headed, root=args.profile_dir) as context:
        page = context.new_page()
        page.goto(args.url, wait_until="domcontentloaded")
        observed = page.evaluate(PROBE)
        detector = None
        if args.fpjs:
            from verify import fingerprintjs

            detector = fingerprintjs.read(page)
    problems = diff(profile, observed)
    print(json.dumps({
        "profile": profile.name,
        "observed": observed,
        "problems": problems,
        "fingerprintjs": detector,
    }, indent=2, default=str))
    return 0 if not problems else 1


def build_parser():
    parser = argparse.ArgumentParser(
        prog="fp-spoof", description="Mint, store and audit browser profiles."
    )
    sub = parser.add_subparsers(dest="command", required=True)

    def add(name, handler):
        child = sub.add_parser(name)
        child.add_argument("--platform", default="windows", choices=sorted(tables.ALLOWED))
        child.add_argument("--browser", default=None)
        child.add_argument("--seed", type=int, default=DEFAULT_SEED)
        child.add_argument("--pool", default=DEFAULT_POOL)
        child.set_defaults(handler=handler)
        return child

    mint_cmd = add("mint", cmd_mint)
    mint_cmd.add_argument("--name", default=None)
    mint_cmd.add_argument("--save", action="store_true")
    add("probe", cmd_probe)
    audit_cmd = add("audit", cmd_audit)
    audit_cmd.add_argument("--n", type=int, default=200)
    live_cmd = add("live", cmd_live)
    live_cmd.add_argument("--url", default="about:blank")
    live_cmd.add_argument("--headed", action="store_true")
    live_cmd.add_argument("--profile-dir", default=None)
    live_cmd.add_argument("--fpjs", action="store_true")

    listing = sub.add_parser("list")
    listing.add_argument("--pool", default=None)
    listing.set_defaults(handler=cmd_list)

    using = sub.add_parser("use")
    using.add_argument("--name", required=True)
    using.add_argument("--pool", default=DEFAULT_POOL)
    using.set_defaults(handler=cmd_use)

    return parser


def main(argv=None):
    args = build_parser().parse_args(argv)
    try:
        return args.handler(args)
    except (MintError, RuntimeError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
