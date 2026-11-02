"""Proxy configuration: parsing, formatting and validation.

People get a proxy from a provider as one URL — ``socks5://user:pass@host:1080``
— not as four form fields, so the CLI and the editor both accept that form and
normalise it into what the extension applies.

A VPN is deliberately *not* modelled as a proxy: it is configured in the
operating system. Choosing ``system`` mode is the honest way to say "route like
the OS does", which is what makes an OS-level VPN take effect.
"""

from __future__ import annotations

import re
from typing import Any, Dict, List, Optional
from urllib.parse import unquote, urlsplit

SCHEMES = ("http", "https", "socks4", "socks5")
MODES = ("fixed_servers", "system", "direct")
DEFAULT_BYPASS = ["localhost", "127.0.0.1"]

_SCHEME_ALIASES = {"socks5h": "socks5", "socks": "socks5"}
_BRACKETED = re.compile(r"^\[(?P<host>[^\]]+)\]:(?P<port>\d{1,5})$")
_PLAIN = re.compile(r"^(?P<host>[^:/]+):(?P<port>\d{1,5})$")


class ProxyError(ValueError):
    """Raised when a proxy string cannot be applied."""


def system() -> Dict[str, Any]:
    return {"mode": "system"}


def direct() -> Dict[str, Any]:
    return {"mode": "direct"}


def is_proxy(proxy: Any) -> bool:
    """True when this payload routes through an actual proxy server."""
    return bool(proxy) and str((proxy or {}).get("mode") or "fixed_servers") == "fixed_servers"


def parse(value: Any) -> Optional[Dict[str, Any]]:
    """Normalise a dict, a provider URL or ``host:port`` into a payload.

    Returns ``None`` for "no proxy configured" (system mode), which is what a
    cleared persona means.
    """
    if value is None or value == "":
        return None

    if isinstance(value, dict):
        mode = str(value.get("mode") or "fixed_servers").lower()
        if mode in ("system", "direct"):
            return {"mode": mode}
        if mode != "fixed_servers":
            raise ProxyError("unknown proxy mode %r" % mode)
        scheme = str(value.get("scheme") or "http").lower()
        host = str(value.get("host") or "").strip()
        port = value.get("port")
        username = value.get("username")
        password = value.get("password")
        bypass = [str(item).strip() for item in (value.get("bypass") or []) if str(item).strip()]
    else:
        text = str(value).strip()
        if "://" in text:
            parts = urlsplit(text)
            scheme = (parts.scheme or "http").lower()
            host = parts.hostname or ""
            port = parts.port
            username = unquote(parts.username) if parts.username else None
            password = unquote(parts.password) if parts.password else None
            bypass = []
        else:
            match = _BRACKETED.match(text) or _PLAIN.match(text)
            if not match:
                raise ProxyError("expected host:port or scheme://[user:pass@]host:port")
            scheme, host, port = "http", match.group("host"), int(match.group("port"))
            username = password = None
            bypass = []

    scheme = _SCHEME_ALIASES.get(scheme, scheme)
    if scheme not in SCHEMES:
        raise ProxyError("scheme must be http, https, socks4 or socks5")
    if not host or any(ch.isspace() for ch in str(host)) or "/" in str(host):
        raise ProxyError("host is required and must not contain spaces or slashes")
    try:
        port = int(port)
    except (TypeError, ValueError):
        raise ProxyError("port must be an integer between 1 and 65535")
    if not 0 < port < 65536:
        raise ProxyError("port must be an integer between 1 and 65535")
    if username is not None and not str(username).strip():
        raise ProxyError("username is empty")

    payload: Dict[str, Any] = {
        "mode": "fixed_servers",
        "scheme": scheme,
        "host": str(host),
        "port": port,
        "bypass": bypass or list(DEFAULT_BYPASS),
    }
    if username is not None:
        payload["username"] = str(username)
        payload["password"] = "" if password is None else str(password)
    return payload


def problems(proxy: Any) -> List[str]:
    """All validation error codes for a payload, without raising."""
    if proxy is None:
        return []
    if not isinstance(proxy, dict):
        return ["proxy-invalid"]
    mode = str(proxy.get("mode") or "fixed_servers").lower()
    if mode not in MODES:
        return ["proxy-mode"]
    if mode != "fixed_servers":
        return []
    out: List[str] = []
    scheme = _SCHEME_ALIASES.get(str(proxy.get("scheme") or "http").lower(), str(proxy.get("scheme") or "http").lower())
    if scheme not in SCHEMES:
        out.append("proxy-scheme")
    host = str(proxy.get("host") or "").strip()
    if not host or any(ch.isspace() for ch in host) or "/" in host:
        out.append("proxy-host")
    try:
        port = int(proxy.get("port"))
    except (TypeError, ValueError):
        out.append("proxy-port")
    else:
        if not 0 < port < 65536:
            out.append("proxy-port")
    username = proxy.get("username")
    if username is not None and not str(username).strip():
        out.append("proxy-username")
    return out


def proxy_url(proxy: Any) -> str:
    """``scheme://host:port`` without credentials, for display and logs."""
    if not is_proxy(proxy):
        return ""
    payload = parse(proxy)
    return "%s://%s:%d" % (payload["scheme"], payload["host"], payload["port"])


def describe(proxy: Any) -> str:
    if proxy is None:
        return "system / VPN (no proxy configured)"
    mode = str((proxy or {}).get("mode") or "fixed_servers").lower()
    if mode == "system":
        return "system / VPN (no proxy configured)"
    if mode == "direct":
        return "direct (system proxy ignored)"
    payload = parse(proxy)
    auth = " with credentials" if payload.get("username") else ""
    return "%s%s" % (proxy_url(payload), auth)
