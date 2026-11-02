"""``fps`` command line interface."""

from __future__ import annotations

import argparse
import json
import os
import random
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

from fix.reconcile import describe, reconcile
from fpr import catalog, egress, geo as geodata, net, vpn
from fpr.fingerprint import entropy_bits, gen, mean_distance
from models import store
from verify.fingerprintjs_vX import fingerprint
from verify.score import score as acceptance

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_EXTENSION_DIR = ROOT / "extension"


def extension_dir() -> Path:
    """Extension directory.

    Overridable with ``FPSPOOF_EXTENSION`` so tests cannot clobber the
    mirror inside the working tree.
    """
    override = os.environ.get("FPSPOOF_EXTENSION")
    return Path(override).expanduser() if override else DEFAULT_EXTENSION_DIR


# --------------------------------------------------------------------------
# helpers
# --------------------------------------------------------------------------

def _persona_line(row: Dict[str, Any]) -> str:
    persona = row.get("persona") or {}
    return "%-24s %-6s %-8s %5sx%-5s dpr %-4s mem %-4s cores %-2s %6.1f bits %4.2f score" % (
        row.get("name", "?"),
        row.get("browser", "?"),
        row.get("platform", "?"),
        persona.get("screenX", "?"),
        persona.get("screenY", "?"),
        persona.get("pixelRatio", "?"),
        persona.get("deviceMemory", "-"),
        persona.get("hardwareConcurrency", "?"),
        float(row.get("entropy_bits") or 0.0),
        float(row.get("score") or 0.0),
    )




def write_geo_mirror() -> Path:
    """Publish the location table next to the extension.

    The advanced editor warns about coordinates that disagree with the timezone,
    so it needs the same city table the generator used. Copying it keeps one
    source of truth instead of a second, drifting list in JavaScript.
    """
    path = extension_dir() / "geo.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        previous = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        previous = {}
    cities = geodata.cities()
    # Keep the stamp from the run that last changed the table. Otherwise every
    # clean gate would dirty a tracked file just by regenerating it.
    unchanged = previous.get("cities") == cities and isinstance(previous.get("updated"), str)
    payload = {
        "updated": previous["updated"] if unchanged else
        datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "cities": cities,
    }
    text = json.dumps(payload, indent=2, sort_keys=True)
    if not path.exists() or path.read_text(encoding="utf-8") != text:
        path.write_text(text, encoding="utf-8")
    return path


def mirror_path() -> Path:
    return extension_dir() / "personas.json"


def write_mirror(extra: Optional[Dict[str, Dict[str, Any]]] = None) -> Path:
    """Publish stored personas to the extension.

    The extension service worker reads this file so ``fps gen`` in a terminal is
    immediately visible in the popup, without a network round trip.
    """
    rows = store.list_profiles()
    personas: Dict[str, Dict[str, Any]] = {}
    for row in rows:
        persona = row.get("persona") or {}
        personas[row["name"]] = persona
    if extra:
        personas.update(extra)
    write_geo_mirror()
    path = mirror_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        previous = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        previous = {}
    # Keep the shipped default across regenerations when it still exists.
    # Store iteration order follows row ids, which a clean gate can recreate
    # differently; that must not rewrite a tracked file.
    default = (previous.get("default")
               if previous.get("default") in personas
               else next(iter(personas), None))
    unchanged = (previous.get("default") == default and
                 previous.get("personas") == personas and
                 isinstance(previous.get("updated"), str))
    payload = {
        "updated": previous["updated"] if unchanged else
        datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "default": default,
        "personas": personas,
    }
    text = json.dumps(payload, separators=(",", ":"), sort_keys=True, default=str)
    if not path.exists() or path.read_text(encoding="utf-8") != text:
        path.write_text(text, encoding="utf-8")

    # The static MAIN-world content script reads this synchronously at
    # document_start, before any page script runs. Rewriting it on every
    # `fps gen` is what makes early application possible without storage I/O.
    default_persona = personas.get(payload["default"]) if payload["default"] else None
    bomb = extension_dir() / "src" / "persona.js"
    bomb.parent.mkdir(parents=True, exist_ok=True)
    bomb_text = (
        "/* Generated by `fps gen`; applied at document_start. */\n"
        "window.__FPS_PERSONA__ = window.__FPS_PERSONA__ || %s;\n"
        % json.dumps(default_persona, sort_keys=True, default=str)
    )
    if not bomb.exists() or bomb.read_text(encoding="utf-8") != bomb_text:
        bomb.write_text(bomb_text, encoding="utf-8")
    return path


# --------------------------------------------------------------------------
# commands
# --------------------------------------------------------------------------

def cmd_gen(args: argparse.Namespace) -> int:
    combos: List[tuple] = []
    if args.all:
        combos = catalog.combos()
    else:
        combos = [(args.browser, args.platform)]
        if args.platform not in catalog.platforms_for(args.browser):
            print(
                "error: %r is not available on %r (supported: %s)"
                % (args.browser, args.platform, ", ".join(catalog.platforms_for(args.browser))),
                file=sys.stderr,
            )
            return 2

    created: List[Dict[str, Any]] = []
    rejected: List[tuple] = []
    for browser, platform in combos:
        for index in range(args.count):
            seed = args.seed + index
            persona = gen(
                random.Random(seed), browser, platform
            )
            ok, details = acceptance(persona)
            if not ok:
                rejected.append(("%s/%s seed=%d" % (browser, platform, seed), details.get("reason")))
                continue
            name = args.name if (args.name and args.count == 1 and len(combos) == 1) else "%s-%s-%04d" % (browser, platform, seed)
            persona["name"] = name
            store.upsert(
                name=name,
                pool=args.pool,
                browser=browser,
                platform=platform,
                entropy=details["bits"],
                fpjs=details["fpjs"],
                persona=persona,
            )
            created.append(
                {
                    "name": name,
                    "browser": browser,
                    "platform": platform,
                    "entropy_bits": details["bits"],
                    "score": details["fpjs"],
                    "persona": persona,
                }
            )

    if args.json:
        print(json.dumps(created, indent=2, default=str))
    else:
        for row in created:
            print(_persona_line(row))
        print(
            "%d profile(s) written to %s"
            % (len(created), store.db_path())
        )
    for name, reason in rejected:
        print("rejected %s: %s" % (name, ", ".join(reason or [])), file=sys.stderr)

    if created and not args.no_sync:
        path = write_mirror()
        if not args.json:
            print("extension mirror updated: %s" % path)
    return 0 if not rejected else 1


def cmd_list(args: argparse.Namespace) -> int:
    rows = store.list_profiles(args.pool)
    if args.json:
        print(json.dumps(rows, indent=2, default=str))
        return 0
    if not rows:
        print("no profiles yet — run: fps gen")
        return 0
    for row in rows:
        print(_persona_line(row))
    print("%d profile(s) in %s" % (len(rows), store.db_path()))
    return 0


def cmd_show(args: argparse.Namespace) -> int:
    row = store.get(args.name)
    if row is None:
        print("error: no profile named %r" % args.name, file=sys.stderr)
        return 1
    if args.json:
        print(json.dumps(row, indent=2, default=str))
        return 0
    persona = row.get("persona") or {}
    print("name        %s" % row["name"])
    print("pool        %s" % row["pool"])
    print("browser     %s %s" % (row["browser"], persona.get("version", "")))
    print("platform    %s (%s, %s)" % (row["platform"], persona.get("platformKey"), persona.get("architecture")))
    print("screen      %sx%s @ %sx (avail %sx%s)" % (
        persona.get("screenX"), persona.get("screenY"), persona.get("pixelRatio"),
        persona.get("availX"), persona.get("availY")))
    memory = persona.get("deviceMemory")
    print("hardware    %s cores, %s, %s touch" % (
        persona.get("hardwareConcurrency"),
        "n/a" if memory is None else "%s GB" % memory,
        persona.get("maxTouchPoints")))
    print("locale      %s / %s" % (",".join(persona.get("languagesZ") or []), persona.get("timezone")))
    print("gpu         %s" % persona.get("webglRenderer"))
    print("ua          %s" % persona.get("ua"))
    print("entropy     %.1f bits" % (row.get("entropy_bits") or 0))
    print("score       %.2f" % (row.get("score") or 0))
    print("consistency %s" % describe(persona))
    return 0


def cmd_validate(args: argparse.Namespace) -> int:
    rows = store.list_profiles()
    if args.name:
        row = store.get(args.name)
        if row is None:
            print("error: no profile named %r" % args.name, file=sys.stderr)
            return 1
        rows = [row]
    if not rows:
        print("no profiles to validate — run: fps gen", file=sys.stderr)
        return 1

    failures = 0
    report = []
    for row in rows:
        persona = row.get("persona") or {}
        problems = reconcile(persona)
        ok, details = acceptance(persona)
        if not ok:
            failures += 1
        entry = {
            "name": row["name"],
            "ok": ok,
            "errors": problems,
            "score": details["fpjs"],
            "bits": details["bits"],
            "reason": details.get("reason"),
        }
        report.append(entry)
        if not args.json:
            print("%-24s %-4s %4.2f score %5.1f bits %s" % (
                row["name"], "ok" if ok else "FAIL", details["fpjs"], details["bits"],
                ", ".join(problems) or "-"))
    if args.json:
        print(json.dumps(report, indent=2))
        return 0 if failures == 0 else 1
    print("%d/%d valid" % (len(rows) - failures, len(rows)))
    return 0 if failures == 0 else 1


def cmd_delete(args: argparse.Namespace) -> int:
    if not store.delete(args.name):
        print("error: no profile named %r" % args.name, file=sys.stderr)
        return 1
    write_mirror()
    print("deleted %s" % args.name)
    return 0


def cmd_export(args: argparse.Namespace) -> int:
    rows = store.list_profiles(args.pool)
    if not rows:
        print("no profiles to export — run: fps gen", file=sys.stderr)
        return 1
    payload = {
        "version": 1,
        "exported": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "default": rows[0]["name"],
        "personas": {row["name"]: row.get("persona") or {} for row in rows},
    }
    if args.out:
        out = Path(args.out).expanduser()
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(payload, indent=2, default=str), encoding="utf-8")
        print("wrote %s (%d personas)" % (out, len(rows)))
    else:
        print(json.dumps(payload, indent=2, default=str))
    return 0


def cmd_stats(args: argparse.Namespace) -> int:
    rows = store.list_profiles()
    if not rows:
        print("no profiles — run: fps gen")
        return 0
    bits = [float(r.get("entropy_bits") or 0) for r in rows]
    scores = [float(r.get("score") or 0) for r in rows]
    print("profiles        %d" % len(rows))
    print("database        %s" % store.db_path())
    print("entropy bits    min %.1f  mean %.1f  max %.1f" % (min(bits), sum(bits) / len(bits), max(bits)))
    print("coherence score min %.2f  mean %.2f  max %.2f" % (min(scores), sum(scores) / len(scores), max(scores)))
    distinct = len({json.dumps(r.get("persona") or {}, sort_keys=True, default=str) for r in rows})
    print("distinct        %d" % distinct)
    for browser, platform in catalog.combos():
        print("spread %-6s %-8s %.3f" % (browser, platform, mean_distance(n=48, browser=browser, platform=platform)))
    return 0


def cmd_launch(args: argparse.Namespace) -> int:
    from launcher.launch import LaunchError, chrome_path, launch

    row = store.get(args.name) if args.name else None
    if args.name and row is None:
        print("error: no profile named %r" % args.name, file=sys.stderr)
        return 1
    if row is None:
        rows = store.list_profiles()
        if rows:
            row = rows[0]
        else:
            persona = gen(random.Random(0), args.browser, args.platform)
            row = {"name": "(ephemeral)", "persona": persona}

    persona = row.get("persona") or {}
    if not persona:
        print("error: profile %r has no persona payload" % row.get("name"), file=sys.stderr)
        return 1

    proxy = persona.get("proxy") or None
    if getattr(args, "proxy", None):
        try:
            proxy = net.parse(args.proxy)
        except net.ProxyError as exc:
            print("error: %s" % exc, file=sys.stderr)
            return 1

    binary = args.chrome or chrome_path()
    if not binary:
        print("error: no Chrome/Chromium/Brave/Edge found; pass --chrome PATH", file=sys.stderr)
        return 1
    if args.dry_run:
        print("chrome   %s" % binary)
        print("profile  %s" % row["name"])
        print("ua       %s" % persona.get("ua"))
        print("screen   %sx%s @ %sx" % (persona.get("screenX"), persona.get("screenY"), persona.get("pixelRatio")))
        print("extension %s" % (extension_dir() if not args.no_extension else "(disabled)"))
        print("proxy    %s" % ("%s://%s:%s" % (proxy["scheme"], proxy["host"], proxy["port"])
                                if proxy else "none (real egress IP)"))
        return 0

    extension = None if args.no_extension else str(extension_dir())
    if extension and not (extension_dir() / "manifest.json").exists():
        print("warning: %s has no manifest.json; launching without the extension" % extension_dir(), file=sys.stderr)
        extension = None

    print("launching %s as %s ..." % (Path(binary).name, row.get("name")))
    try:
        session = launch(
            persona,
            url=args.url,
            headless=args.headless,
            extension=extension,
            chrome=binary,
            proxy=proxy,
        )
    except LaunchError as exc:
        print("error: %s" % exc, file=sys.stderr)
        return 1

    if session.extension_id:
        print("extension   %s" % session.extension_id)
    elif extension:
        print("warning: extension did not mount (%s)" % (session.extension_error or "unknown"),
              file=sys.stderr)
    print("profile dir %s" % session.profile_dir)
    print("browser is running — close it to exit")
    try:
        session.wait()
    except KeyboardInterrupt:
        pass
    finally:
        session.close()
    return 0


def cmd_verify(args: argparse.Namespace) -> int:
    from launcher.launch import LaunchError, chrome_path, verify_persona

    binary = args.chrome or chrome_path()
    if not binary:
        print("error: no Chrome/Chromium/Brave/Edge found; pass --chrome PATH", file=sys.stderr)
        return 1

    restore_mirror: Optional[str] = None
    if args.extension:
        try:
            mirror = json.loads((extension_dir() / "personas.json").read_text())
        except (OSError, ValueError):
            mirror = {}
        name = getattr(args, "name", None) or mirror.get("default")
        persona = (mirror.get("personas") or {}).get(name) if name else None
        if not persona:
            print("error: extension/personas.json has no personas — run: fps gen", file=sys.stderr)
            return 1
        other = None
        if getattr(args, "name", None):
            mirror_file = extension_dir() / "personas.json"
            restore_mirror = mirror_file.read_text(encoding="utf-8")
            mirror["default"] = name
            mirror_file.write_text(
                json.dumps(mirror, separators=(",", ":"), sort_keys=True),
                encoding="utf-8")
        print("using the extension's persona: %s" % name)
    else:
        persona = gen(random.Random(args.seed), args.browser, args.platform)
        other = gen(random.Random(args.seed + 1), args.browser, args.platform)

    print("verifying %s on %s in %s" % (args.browser, args.platform, Path(binary).name))
    try:
        result = verify_persona(
            persona,
            chrome=binary,
            headless=not args.headful,
            other_persona=other,
            extension=str(extension_dir()) if args.extension else None,
        )
    except LaunchError as exc:
        print("error: %s" % exc, file=sys.stderr)
        return 1
    finally:
        # Verification picks a persona; it must not leave the shipped default
        # rewritten, or a clean green run would dirty the tree it just checked.
        if restore_mirror is not None:
            (extension_dir() / "personas.json").write_text(
                restore_mirror, encoding="utf-8")

    if args.json:
        print(json.dumps(result, indent=2, default=str))
    else:
        print("%-22s %-14s %-40s %s" % ("CHECK", "EXPECTED", "ACTUAL", "RESULT"))
        for check in result["checks"]:
            print("%-22s %-14s %-40s %s" % (
                check["name"],
                str(check["expected"])[:14],
                str(check["actual"])[:40],
                "ok" if check["ok"] else "FAIL",
            ))
    passed = sum(1 for c in result["checks"] if c["ok"])
    total = len(result["checks"])
    print("%d/%d checks passed" % (passed, total))
    return 0 if passed == total else 1


def cmd_extension(args: argparse.Namespace) -> int:
    print(extension_dir())
    if not (extension_dir() / "manifest.json").exists():
        print("warning: no manifest.json found", file=sys.stderr)
        return 1
    if args.sync:
        path = write_mirror()
        print("personas synced: %s" % path)
    return 0


def cmd_geo(args: argparse.Namespace) -> int:
    if args.lat is not None or args.lon is not None:
        if args.lat is None or args.lon is None:
            print("error: pass both --lat and --lon", file=sys.stderr)
            return 1
        found = geodata.nearest(args.lat, args.lon)
        if not found:
            print("error: the location table is empty", file=sys.stderr)
            return 1
        zone, entry, span = found
        if args.json:
            print(json.dumps({"timezone": zone, "city": entry, "distance_km": span}, indent=2))
        else:
            print("%s, %s" % (entry.get("city"), entry.get("country")))
            print("timezone   %s" % zone)
            print("coords     %.4f, %.4f" % (entry["latitude"], entry["longitude"]))
            print("distance   %.0f km from the point you gave" % span)
        return 0

    if not args.timezone:
        print("error: pass a timezone, or --lat/--lon", file=sys.stderr)
        return 1
    entry = geodata.city(args.timezone)
    if entry is None:
        print("error: no city for %r; known zones: %s"
              % (args.timezone, ", ".join(sorted(geodata.cities()))), file=sys.stderr)
        return 1
    if args.json:
        print(json.dumps(entry, indent=2, sort_keys=True))
    else:
        print("%-22s %s, %s  %.4f, %.4f" % (args.timezone, entry.get("city"),
                                            entry.get("country"), entry["latitude"],
                                            entry["longitude"]))
    return 0


def cmd_proxy(args: argparse.Namespace) -> int:
    row = store.get(args.name)
    if row is None:
        print("error: no profile named %r" % args.name, file=sys.stderr)
        return 1
    persona = dict(row.get("persona") or {})
    if args.clear:
        persona["proxy"] = None
    elif args.system:
        persona["proxy"] = net.system()
    elif args.direct:
        persona["proxy"] = net.direct()
    else:
        raw = args.url
        if raw is None:
            if not args.host or args.port is None:
                print("error: pass --url, --host/--port, --system, --direct or --clear",
                      file=sys.stderr)
                return 1
            raw = {"scheme": args.scheme, "host": args.host, "port": args.port}
        if args.bypass:
            raw = dict(raw) if isinstance(raw, dict) else raw
            bypass = [item.strip() for item in args.bypass.split(",") if item.strip()]
            if isinstance(raw, dict):
                raw["bypass"] = bypass
        try:
            proxy = net.parse(raw)
        except net.ProxyError as exc:
            print("error: %s" % exc, file=sys.stderr)
            return 1
        if isinstance(raw, str) and args.bypass:
            proxy["bypass"] = [item.strip() for item in args.bypass.split(",") if item.strip()]
        if args.username:
            proxy["username"] = args.username
            proxy["password"] = args.password or ""
        problems = net.problems(proxy)
        if problems:
            print("error: %s" % ", ".join(problems), file=sys.stderr)
            return 1
        persona["proxy"] = proxy

    store.upsert(
        name=args.name,
        pool=row.get("pool") or "default",
        browser=row.get("browser") or "chrome",
        platform=row.get("platform") or "windows",
        entropy=float(row.get("entropy_bits") or 0.0),
        fpjs=float(row.get("score") or 0.0),
        persona=persona,
    )
    write_mirror()
    print("%s -> %s" % (args.name, net.describe(persona.get("proxy"))))
    return 0


def cmd_vpn(args: argparse.Namespace) -> int:
    payload = vpn.summary()
    if getattr(args, "sync", False):
        target = extension_dir() / "data" / "vpn.json"
        vpn.write_mirror(payload, target)
        if not args.json:
            print("wrote %s" % target)
    if args.json:
        print(json.dumps(payload, indent=2, sort_keys=True))
        return 0
    for tunnel in payload["tunnels"]:
        print("%-12s %-14s %s" % (tunnel["label"], tunnel["state"], tunnel["detail"]))
    print("tunnel interfaces: %s" % (", ".join(payload["interfaces"]) or "none"))
    print("A tunnel is started by its own client; this only reads what it reports.")
    return 0


def cmd_egress(args: argparse.Namespace) -> int:
    row = store.get(args.name)
    if row is None:
        print("error: no profile named %r" % args.name, file=sys.stderr)
        return 1
    try:
        result = egress.compare({}, row.get("persona") or {}, endpoint=args.endpoint)
    except egress.EgressError as exc:
        print("error: %s" % exc, file=sys.stderr)
        return 1
    if args.json:
        print(json.dumps(result, indent=2, sort_keys=True))
        return 0
    observed = result["observed"]
    print("egress   %s  %s, %s  %s" % (observed["ip"], observed["city"],
                                      observed["country"], observed["org"] or ""))
    persona = result["persona"]
    print("persona  %s  %s" % (persona["city"], persona["timezone"]))
    if result["distance_km"] is not None:
        print("distance %d km" % result["distance_km"])
    for note in result["notes"]:
        print("note     %s" % note)
    return 0


def cmd_diff(args: argparse.Namespace) -> int:
    left = store.get(args.left)
    right = store.get(args.right)
    for label, row in ((args.left, left), (args.right, right)):
        if row is None:
            print("error: no profile named %r" % label, file=sys.stderr)
            return 1
    a = left.get("persona") or {}
    b = right.get("persona") or {}
    keys = sorted(set(a) | set(b))
    differing = [key for key in keys if json.dumps(a.get(key), sort_keys=True, default=str) !=
                 json.dumps(b.get(key), sort_keys=True, default=str)]
    if args.json:
        print(json.dumps({key: {"left": a.get(key), "right": b.get(key)} for key in differing},
                         indent=2, default=str))
        return 0
    print("%-22s %-34s %-34s" % ("FIELD", args.left, args.right))
    for key in differing:
        print("%-22s %-34s %-34s" % (key, str(a.get(key))[:34], str(b.get(key))[:34]))
    print("%d field(s) differ of %d" % (len(differing), len(keys)))
    return 0


def _next_profile_name(browser: str, platform: str) -> str:
    """Next free ``browser-platform-NNNN`` name, so rolls never overwrite."""
    prefix = "%s-%s-" % (browser, platform)
    highest = -1
    for row in store.list_profiles():
        name = str(row.get("name") or "")
        if name.startswith(prefix) and name[len(prefix):].isdigit():
            highest = max(highest, int(name[len(prefix):]))
    return "%s%04d" % (prefix, highest + 1)


def cmd_roll(args: argparse.Namespace) -> int:
    """Generate one whole new identity.

    The point is that every field is drawn together by the generator and then
    validated before it is stored: a roll can never be a mix of two devices.
    """
    rng = random.Random(args.seed) if args.seed is not None else random.SystemRandom()
    persona = gen(rng, args.browser, args.platform)
    problems = reconcile(persona)
    if problems:
        print("error: generated persona is incoherent: %s" % ", ".join(problems), file=sys.stderr)
        return 1

    name = args.name or _next_profile_name(args.browser, args.platform)
    if store.get(name):
        print("error: profile %r already exists; omit --name to roll the next one" % name,
              file=sys.stderr)
        return 1

    accepted, details = acceptance(persona)
    store.upsert(
        name=name,
        pool=args.pool,
        browser=args.browser,
        platform=args.platform,
        entropy=float(details.get("bits") or 0.0),
        fpjs=float(details.get("fpjs") or 0.0),
        persona=persona,
    )
    if not args.no_sync:
        write_mirror()

    geo = persona.get("geo") or {}
    if args.json:
        print(json.dumps({"name": name, "persona": persona, "accepted": accepted}, indent=2, default=str))
    else:
        print("%-22s %s %s  %sx%s  %s  %.4f, %.4f" % (
            name, persona["browser"], persona["platform"],
            persona["screenX"], persona["screenY"], persona["timezone"],
            geo.get("latitude", 0.0), geo.get("longitude", 0.0)))
        print("whole identity regenerated (%s) and stored" % ("accepted" if accepted else "with warnings"))
    return 0


# --------------------------------------------------------------------------
# parser
# --------------------------------------------------------------------------

def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="fps",
        description="Generate and apply coherent browser-fingerprint personas offline.",
    )
    sub = parser.add_subparsers(dest="command")

    gen = sub.add_parser("gen", help="generate and store personas")
    gen.add_argument("-n", "--count", type=int, default=1)
    gen.add_argument("-b", "--browser", default="chrome", choices=sorted(catalog.browsers()))
    gen.add_argument("-p", "--platform", default="windows", choices=["windows", "mac", "linux", "ios"])
    gen.add_argument("--all", action="store_true", help="one persona per supported browser/platform pair")
    gen.add_argument("--seed", type=int, default=0)
    gen.add_argument("--pool", default="default")
    gen.add_argument("--name", default=None)
    gen.add_argument("--json", action="store_true")
    gen.add_argument("--no-sync", action="store_true", help="do not refresh extension/personas.json")
    gen.set_defaults(handler=cmd_gen)

    lst = sub.add_parser("list", help="list stored personas")
    lst.add_argument("--pool", default=None)
    lst.add_argument("--json", action="store_true")
    lst.set_defaults(handler=cmd_list)

    show = sub.add_parser("show", help="show one persona in detail")
    show.add_argument("name")
    show.add_argument("--json", action="store_true")
    show.set_defaults(handler=cmd_show)

    val = sub.add_parser("validate", help="re-check stored personas")
    val.add_argument("name", nargs="?")
    val.add_argument("--json", action="store_true")
    val.set_defaults(handler=cmd_validate)

    delete = sub.add_parser("delete", help="remove a persona")
    delete.add_argument("name")
    delete.set_defaults(handler=cmd_delete)

    export = sub.add_parser("export", help="export personas as JSON")
    export.add_argument("--out", default=None)
    export.add_argument("--pool", default=None)
    export.set_defaults(handler=cmd_export)

    stats = sub.add_parser("stats", help="entropy and diversity summary")
    stats.set_defaults(handler=cmd_stats)

    launch = sub.add_parser("launch", help="start Chrome with a persona applied")
    launch.add_argument("name", nargs="?")
    launch.add_argument("--url", default="about:blank")
    launch.add_argument("--chrome", default=None)
    launch.add_argument("--browser", default="chrome")
    launch.add_argument("--platform", default="windows")
    launch.add_argument("--headless", action="store_true")
    launch.add_argument("--no-extension", action="store_true")
    launch.add_argument("--dry-run", action="store_true")
    launch.add_argument("--proxy", default=None, metavar="HOST:PORT",
                        help="override the persona's proxy for this launch")
    launch.set_defaults(handler=cmd_launch)

    verify = sub.add_parser("verify", help="apply a persona in a real browser and check it")
    verify.add_argument("--browser", default="chrome")
    verify.add_argument("--platform", default="windows")
    verify.add_argument("--chrome", default=None)
    verify.add_argument("--seed", type=int, default=111)
    verify.add_argument("--headful", action="store_true")
    verify.add_argument("--name", default=None, help="persona to load when --extension is used")
    verify.add_argument("--extension", action="store_true",
                        help="also load the unpacked extension and check document_start injection")
    verify.add_argument("--json", action="store_true")
    verify.set_defaults(handler=cmd_verify)

    roll = sub.add_parser("roll", help="generate one whole new identity and store it")
    roll.add_argument("-b", "--browser", default="chrome", choices=sorted(catalog.browsers()))
    roll.add_argument("-p", "--platform", default="windows", choices=["windows", "mac", "linux", "ios"])
    roll.add_argument("--seed", type=int, default=None)
    roll.add_argument("--name", default=None)
    roll.add_argument("--pool", default="default")
    roll.add_argument("--no-sync", action="store_true")
    roll.add_argument("--json", action="store_true")
    roll.set_defaults(handler=cmd_roll)

    geo_cmd = sub.add_parser("geo", help="resolve a timezone to the city a persona carries")
    geo_cmd.add_argument("timezone", nargs="?")
    geo_cmd.add_argument("--lat", type=float, default=None)
    geo_cmd.add_argument("--lon", type=float, default=None)
    geo_cmd.add_argument("--json", action="store_true")
    geo_cmd.set_defaults(handler=cmd_geo)

    proxy_cmd = sub.add_parser("proxy", help="attach or clear a persona's egress proxy")
    proxy_cmd.add_argument("name")
    proxy_cmd.add_argument("--scheme", default="http", choices=["http", "https", "socks4", "socks5"])
    proxy_cmd.add_argument("--host", default=None)
    proxy_cmd.add_argument("--port", type=int, default=None)
    proxy_cmd.add_argument("--bypass", default=None, help="comma-separated hosts that skip the proxy")
    proxy_cmd.add_argument("--url", default=None,
                           help="provider URL: scheme://[user:pass@]host:port")
    proxy_cmd.add_argument("--username", default=None)
    proxy_cmd.add_argument("--password", default=None)
    proxy_cmd.add_argument("--system", action="store_true",
                           help="route like the OS does (this is what lets an OS VPN apply)")
    proxy_cmd.add_argument("--direct", action="store_true", help="ignore the system proxy")
    proxy_cmd.add_argument("--clear", action="store_true", help="remove the proxy entirely")
    proxy_cmd.set_defaults(handler=cmd_proxy)

    vpn_cmd = sub.add_parser("vpn", help="report VPN clients detected on this machine")
    vpn_cmd.add_argument("--json", action="store_true")
    vpn_cmd.add_argument("--sync", action="store_true",
                         help="write extension/data/vpn.json for the editor")
    vpn_cmd.set_defaults(handler=cmd_vpn)

    egress_cmd = sub.add_parser("egress", help="check the observed public IP against a persona")
    egress_cmd.add_argument("name")
    egress_cmd.add_argument("--json", action="store_true")
    egress_cmd.add_argument("--endpoint", default=egress.ENDPOINT)
    egress_cmd.set_defaults(handler=cmd_egress)

    diff_cmd = sub.add_parser("diff", help="show which fields differ between two personas")
    diff_cmd.add_argument("left")
    diff_cmd.add_argument("right")
    diff_cmd.add_argument("--json", action="store_true")
    diff_cmd.set_defaults(handler=cmd_diff)

    extension = sub.add_parser("extension", help="print the extension path")
    extension.add_argument("--sync", action="store_true", help="refresh personas.json first")
    extension.set_defaults(handler=cmd_extension)

    return parser


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    handler = getattr(args, "handler", None)
    if handler is None:
        parser.print_help()
        return 2
    try:
        return handler(args) or 0
    finally:
        store.close()


if __name__ == "__main__":
    sys.exit(main())
