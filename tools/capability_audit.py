"""Map every persona field and CLI capability to a concrete UI control.

This is a static audit, not a claim: it fails loudly when a field has no
control or a control id disappears, so "everything is in the GUI" stays true.
Run: python tools/capability_audit.py
"""

import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
HTML = (ROOT / "extension/src/options.html").read_text()
POPUP = (ROOT / "extension/src/popup.html").read_text()
JS = (ROOT / "extension/src/options.js").read_text()
CLI = (ROOT / "api/cli.py").read_text()

# field -> control ids that edit or display it
FIELDS = {
    "user agent / client hints": ["ro-ua", "ro-brands", "ro-platform"],
    "platform": ["ro-platform", "devices"],
    "browser": ["devices"],
    "screen size": ["screenX", "screenY", "screen"],
    "available area": ["ro-avail"],
    "device pixel ratio": ["pixelRatio"],
    "hardware concurrency": ["hardwareConcurrency"],
    "device memory": ["deviceMemory"],
    "color depth": ["ro-platform"],
    "timezone": ["timezone"],
    "locale / languages": ["languages", "language-add", "language-push"],
    "geolocation": ["geo-place", "geo-lat", "geo-lon", "geo-city"],
    "touch points": ["ro-touch"],
    "WebGL renderer": ["webglRenderer"],
    "canvas noise seed": ["canvasSeed", "canvas-dice"],
    "audio noise seed": ["audioSeed", "audio-dice"],
    "field pins / randomisation": ["locks"],
    "granular shuffles": ["reroll-fields", "shuffle-screen", "shuffle-hardware",
                          "shuffle-graphics", "shuffle-noise"],
    "proxy route": ["proxy-mode", "proxy-url", "proxy-host", "proxy-port"],
    "proxy credentials": ["proxy-username", "proxy-password"],
    "VPN detection": ["vpn-list"],
    "egress check": ["ro-ip", "ro-proxy"],
    "coherence": ["checks", "coherence-count"],
    "applied identity": ["ap-name", "ap-seeds", "ap-overrides", "ap-egress"],
    "save / export": ["save", "export"],
    "profile import": ["import-pick", "import-file", "import-text", "import-apply"],
    "delete / stats / diff": ["delete", "stats-run", "stats-out", "diff-run", "diff-out"],
    "browser verify hand-off": ["verify-run", "verify-note"],
}

CLI_COMMANDS = ["gen", "list", "show", "validate", "delete", "export", "stats",
                "launch", "verify", "roll", "geo", "proxy", "vpn", "egress",
                "diff", "extension"]
CLI_IN_UI = {
    "gen": "devices rail (generated profiles) + Reset/reroll",
    "list": "devices rail",
    "show": "read-outs + Applied card",
    "validate": "Coherence card",
    "delete": "#delete (imported personas; baked ones hand off to fps delete)",
    "export": "#export",
    "stats": "#stats-run rendering #stats-out",
    "launch": "Applied card prints the launch command",
    "verify": "#verify-run, disabled with the exact CLI command (needs the launcher)",
    "roll": "#reroll-fields / #shuffle-* in Advanced; popup Reroll/New + axis shuffles",
    "geo": "#geo-place / #geo-snap",
    "proxy": "#proxy-* controls",
    "vpn": "#vpn-list (fps vpn --sync)",
    "egress": "#ro-ip + fps egress hint",
    "diff": "#diff-run comparing two stored personas in #diff-out",
    "extension": "extension path printed by fps extension",
}

missing = []
rows = []
for field, ids in FIELDS.items():
    absent = [i for i in ids if ('id="%s"' % i) not in HTML and i not in ("devices",)]
    rows.append((field, ", ".join(ids), "ok" if not absent else "MISSING " + ", ".join(absent)))
    missing.extend(absent)

print("%-32s %-46s %s" % ("PERSONA FIELD", "UI CONTROL(S)", "STATE"))
for field, ids, state in rows:
    print("%-32s %-46s %s" % (field, ids[:46], state))
print()
print("CLI command -> UI")
for command in CLI_COMMANDS:
    print("  fps %-10s %s" % (command, CLI_IN_UI.get(command, "unknown")))
print()
print("controls wired in options.js:", len(set(re.findall(r"el\('([a-z0-9-]+)'\)", JS))))
print("popup controls:", ", ".join(sorted(set(re.findall(r'id="([a-z0-9-]+)"', POPUP)))))
print("missing control ids:", len(missing))
raise SystemExit(1 if missing else 0)
