"""The extension's proxy module, executed outside a browser.

The proxy config test covers fixed_servers; this covers the two routing modes
that are not proxies, and the credential path, which is the part a site could
otherwise be handed.
"""

import subprocess
from pathlib import Path

EXTENSION = Path(__file__).resolve().parent.parent / "extension" / "src"

HARNESS = r"""
import { proxyValue, webrtcPolicy, proxyAuth, installProxyAuth } from '%s';

const check = (ok, message) => { if (!ok) { console.error(message); process.exit(1); } };

check(proxyValue({ mode: 'system' }) === null, 'system mode must clear the proxy');
check(proxyValue({ mode: 'direct' }).mode === 'direct', 'direct mode must be explicit');
check(webrtcPolicy({ mode: 'direct' }) === 'default', 'direct keeps the browser default policy');
check(webrtcPolicy({ mode: 'system' }) === 'default', 'system keeps the browser default policy');
check(webrtcPolicy({ host: 'h', port: 1 }) === 'disable_non_proxied_udp', 'a proxy must restrict UDP');
check(proxyAuth({ host: 'h', port: 1 }) === null, 'no credentials when none were set');

const listeners = [];
const api = {
  webRequest: {
    onAuthRequired: {
      addListener: (fn, filter, extra) => listeners.push({ fn, filter, extra })
    }
  }
};
check(installProxyAuth(api, () => ({ username: 'u', password: 'p' })) === true, 'listener must install');
check(installProxyAuth({}, () => null) === false, 'absent webRequest must not throw');

const seen = [];
listeners[0].fn({ isProxy: true }, (value) => seen.push(value));
listeners[0].fn({ isProxy: false }, (value) => seen.push(value));
check(seen[0].authCredentials.username === 'u', 'a proxy challenge must be answered');
check(seen[0].authCredentials.password === 'p', 'the password must be answered');
check(Object.keys(seen[1]).length === 0, 'a site 401 must never receive proxy credentials');
check(listeners[0].extra[0] === 'asyncBlocking', 'the listener must be able to block');

console.log('network modes ok');
""" % (EXTENSION / "network.js").as_uri()


def test_routing_modes_and_proxy_credentials_are_executed():
    result = subprocess.run(
        ["node", "--input-type=module", "-e", HARNESS],
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert result.returncode == 0, result.stderr or result.stdout
    assert "network modes ok" in result.stdout
