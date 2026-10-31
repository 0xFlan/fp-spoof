"""fp-spoof CLI.

    python -m api.run mint  --platform windows --browser chrome --seed 111 --save
    python -m api.run probe --seed 111 --platform windows
    python -m api.run list  [--pool default]
    python -m api.run audit --n 200 --platform windows

Exit codes: 0 accepted, 1 rejected, 2 usage error.
"""
from __future__ import annotations

import argparse
import json
import sys

from constants import DEFAULT_POOL, DEFAULT_SEED
from fpr import entropy
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
        "distinctFingerprints": len({profile.wglRenderer for profile in profiles}),
        "report": report,
        "passes": ok,
        "failures": failures,
    }, indent=2, default=str))

    return 0 if ok and not rejected else 1


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

    add("mint", cmd_mint).add_argument("--name", default=None)
    sub.choices["mint"].add_argument("--save", action="store_true")
    add("probe", cmd_probe)
    add("audit", cmd_audit).add_argument("--n", type=int, default=200)

    listing = sub.add_parser("list")
    listing.add_argument("--pool", default=None)
    listing.set_defaults(handler=cmd_list)
    return parser


def main(argv=None):
    args = build_parser().parse_args(argv)
    try:
        return args.handler(args)
    except MintError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
