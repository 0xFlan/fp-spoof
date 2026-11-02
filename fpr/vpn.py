"""Detected VPN tunnels — observed, never started.

This project cannot bring a tunnel up or verify that one is carrying traffic,
so it does the next honest thing: it looks for the clients people actually run,
reports what those clients say about themselves, and lists the tunnel
interfaces the OS exposes. That feeds the editor's "tunnels on this machine"
readout and the System/VPN route, so a user can pick that route knowingly.
"""

from __future__ import annotations

import json
import platform
import shutil
import subprocess
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

CLIENTS: Tuple[Tuple[str, str, Tuple[str, ...]], ...] = (
    ("mullvad", "Mullvad", ("status", "--json")),
    ("nordvpn", "NordVPN", ("status",)),
    ("protonvpn", "Proton VPN", ("status",)),
    ("tailscale", "Tailscale", ("status", "--json")),
    ("wg", "WireGuard", ("show", "interfaces")),
)

TUNNEL_PREFIXES = ("utun", "ipsec", "wg", "tun", "tap", "ppp")


def _run(binary: str, args: Tuple[str, ...], timeout: float) -> Optional[str]:
    try:
        done = subprocess.run(
            [binary, *args], capture_output=True, text=True, timeout=timeout
        )
    except (OSError, subprocess.SubprocessError):
        return None
    return (done.stdout or "") + (done.stderr or "")


def parse_state(client_id: str, text: str) -> str:
    """Map a client's own words onto connected / mesh / disconnected / unknown.

    Machine-readable output is preferred where the client offers it: Mullvad's
    human line has changed between releases, and Tailscale's `Running` only
    means the mesh is up, not that traffic is tunneled (that needs an exit
    node). Old clients fall back to the anchored text forms.
    """
    body = (text or "").strip()
    if not body:
        return "unknown"
    lower = body.lower()
    if client_id in ("mullvad", "tailscale"):
        try:
            payload = json.loads(body)
        except ValueError:
            payload = None
        if isinstance(payload, dict):
            if client_id == "tailscale":
                if str(payload.get("BackendState") or "") != "Running":
                    return "disconnected"
                return "connected" if payload.get("ExitNodeStatus") else "mesh"
            return str(payload.get("state") or "unknown").lower()
    if client_id == "wg":
        return "connected" if body and "interface" not in lower else "disconnected"
    if client_id in ("nordvpn", "protonvpn"):
        first = (body.splitlines() or [""])[0].strip().lower()
        if first.startswith("status: connected"):
            return "connected"
        if first.startswith("status: disconnected"):
            return "disconnected"
        return "unknown"
    if "disconnected" in lower or "not connected" in lower:
        return "disconnected"
    if "connecting" in lower:
        return "connecting"
    if "connected" in lower:
        return "connected"
    return "unknown"


def detail_line(text: str) -> str:
    for line in (text or "").splitlines():
        line = line.strip()
        if line:
            return line[:120]
    return ""


def _interfaces() -> List[str]:
    names: List[str] = []
    system = platform.system()
    if system == "Darwin":
        out = _run("ifconfig", ("-l",), 2.0) or ""
        names = out.split()
    elif system == "Linux":
        out = _run("ip", ("-o", "link", "show"), 2.0) or ""
        for line in out.splitlines():
            parts = line.split(":")
            if len(parts) > 1:
                names.append(parts[1].strip().split("@")[0])
        if not names:
            names = [p.name for p in Path("/sys/class/net").glob("*")] if Path("/sys/class/net").exists() else []
    else:
        names = []
    return [name for name in names if name.startswith(TUNNEL_PREFIXES)]


def detect(timeout: float = 2.0) -> List[Dict[str, Any]]:
    found: List[Dict[str, Any]] = []
    for client_id, label, args in CLIENTS:
        path = shutil.which(client_id)
        entry: Dict[str, Any] = {
            "id": client_id,
            "label": label,
            "installed": bool(path),
            "state": "not installed",
            "detail": "",
        }
        if path:
            text = _run(client_id, args, timeout) or ""
            entry["state"] = parse_state(client_id, text)
            entry["detail"] = detail_line(text)
        found.append(entry)
    return found


def summary(timeout: float = 2.0) -> Dict[str, Any]:
    tunnels = detect(timeout)
    interfaces = _interfaces()
    connected = [t["label"] for t in tunnels if t["state"] == "connected"]
    return {
        "tunnels": tunnels,
        "interfaces": interfaces,
        "active": bool(connected or interfaces),
        "connected": connected,
    }


def write_mirror(summary_payload: Dict[str, Any], target: Path) -> Path:
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(summary_payload, indent=2, sort_keys=True) + "\n")
    return target
