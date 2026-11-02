"""Extension and injection-script asset tests."""

import json
import shutil
import subprocess
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
EXTENSION = REPO / "extension"


def test_manifest_is_mv3():
    manifest = json.loads((EXTENSION / "manifest.json").read_text())
    assert manifest["manifest_version"] == 3
    assert manifest["background"]["service_worker"] == "src/background.js"
    assert "declarativeNetRequest" in manifest["permissions"]
    assert "<all_urls>" in manifest["host_permissions"]


def test_manifest_injects_main_world_at_document_start():
    manifest = json.loads((EXTENSION / "manifest.json").read_text())
    scripts = manifest.get("content_scripts") or []
    assert scripts, "no content_scripts declared"
    entry = scripts[0]
    assert entry["world"] == "MAIN"
    assert entry["run_at"] == "document_start"
    assert entry["js"][0] == "src/persona.js"
    assert "src/patch.js" in entry["js"]
    assert entry["matches"] == ["<all_urls>"]
    assert entry["all_frames"] is True


def test_persona_bomb_exists():
    source = (EXTENSION / "src" / "persona.js").read_text()
    assert "__FPS_PERSONA__" in source


def test_manifest_referenced_files_exist():
    manifest = json.loads((EXTENSION / "manifest.json").read_text())
    referenced = [
        manifest["background"]["service_worker"],
        manifest["action"]["default_popup"],
    ]
    referenced.extend(manifest["icons"].values())
    for entry in manifest.get("content_scripts") or []:
        referenced.extend(entry["js"])
    referenced.extend(manifest["action"]["default_icon"].values())
    for relative in referenced:
        assert (EXTENSION / relative).exists(), relative


def test_patch_script_exposes_the_apply_hook():
    source = (EXTENSION / "src" / "patch.js").read_text()
    assert "__FPS_APPLY__" in source
    assert "__FPS_PERSONA__" in source
    for field in ("userAgent", "hardwareConcurrency", "webglRenderer", "getTimezoneOffset", "toDataURL"):
        assert field in source, field


def test_personas_mirror_is_valid_json():
    payload = json.loads((EXTENSION / "personas.json").read_text())
    assert set(payload) >= {"default", "personas"}


@pytest.mark.skipif(shutil.which("node") is None, reason="node not installed")
@pytest.mark.parametrize(
    "relative",
    ["src/patch.js", "src/background.js", "src/network.js", "src/popup.js",
     "src/schema.js", "src/options.js", "src/persona.js"],
)
def test_javascript_parses(relative):
    result = subprocess.run(
        ["node", "--check", str(EXTENSION / relative)],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr


def test_manifest_declares_a_full_tab_options_page():
    """A popup is destroyed on every close, so the editor lives in a real tab."""
    manifest = json.loads((EXTENSION / "manifest.json").read_text())
    options = manifest.get("options_ui") or {}
    assert options.get("page") == "src/options.html"
    assert options.get("open_in_tab") is True
    assert (EXTENSION / options["page"]).exists()


def test_manifest_referenced_files_exist_includes_options():
    manifest = json.loads((EXTENSION / "manifest.json").read_text())
    page = manifest["options_ui"]["page"]
    assert (EXTENSION / page).exists()


def test_popup_offers_a_whole_identity_roll_and_a_route_to_network():
    html = (EXTENSION / "src" / "popup.html").read_text()
    assert 'id="reshuffle"' in html
    assert 'id="network-link"' in html
    popup = (EXTENSION / "src" / "popup.js").read_text()
    assert "nextIdentity" in popup
    assert "#network" in popup


def test_pages_load_module_scripts_and_no_inline_handlers():
    for relative in ("src/popup.html", "src/options.html"):
        html = (EXTENSION / relative).read_text()
        assert 'type="module"' in html, relative
        assert "onclick=" not in html and "onchange=" not in html, relative


def test_every_surface_shares_one_schema_module():
    schema = (EXTENSION / "src" / "schema.js").read_text()
    for name in ("mergePersona", "check", "summarise", "diffPersona",
                 "rerollCandidates", "rotateSeeds", "LOCKABLE"):
        assert "export" in schema and name in schema, name
    for relative in ("src/popup.js", "src/options.js", "src/background.js"):
        assert "from './schema.js'" in (EXTENSION / relative).read_text(), relative


def test_manifest_can_apply_a_proxy_and_block_webrtc_leaks():
    manifest = json.loads((EXTENSION / "manifest.json").read_text())
    assert "proxy" in manifest["permissions"]
    assert "privacy" in manifest["permissions"]


def test_background_delegates_proxy_work_to_the_executed_module():
    background = (EXTENSION / "src" / "background.js").read_text()
    network = (EXTENSION / "src" / "network.js").read_text()
    assert "from './network.js'" in background
    assert "self.__FPS_APPLY_NETWORK__ = async (api, persona)" in background
    assert "await self.__FPS_APPLY_NETWORK__(chrome, persona)" in background
    assert "installProxyAuth(chrome, () => activeProxy)" in background
    assert "chrome.proxy.settings" not in background, \
        "proxy logic must live in the module the Node harness executes"
    assert "settings.set(" in network and "settings.clear(" in network
    assert "fixed_servers" in network
    assert "webRTCIPHandlingPolicy" in network
    assert "disable_non_proxied_udp" in network


PROXY_HARNESS = r"""import { applyNetwork, proxyConfig, webrtcPolicy } from './network.mjs';

const assert = (ok, message) => { if (!ok) throw new Error(message); };
const calls = [];
const api = {
  proxy: { settings: {
    set: async (arg) => { calls.push({ api: 'proxy.set', arg }); },
    clear: async (arg) => { calls.push({ api: 'proxy.clear', arg }); }
  } },
  privacy: { network: { webRTCIPHandlingPolicy: {
    set: async (arg) => { calls.push({ api: 'webrtc', arg }); }
  } } }
};

const persona = { proxy: { scheme: 'socks5', host: '10.0.0.5', port: 1080, bypass: ['localhost'] } };
const applied = await applyNetwork(api, persona);

assert(calls.length === 2, 'expected two settings writes, got ' + calls.length);
assert(calls[0].api === 'proxy.set', 'proxy must be written first');
assert(calls[0].arg.value.mode === 'fixed_servers', 'mode must be fixed_servers');
assert(calls[0].arg.value.rules.singleProxy.scheme === 'socks5', 'scheme must survive');
assert(calls[0].arg.value.rules.singleProxy.host === '10.0.0.5', 'host must survive');
assert(calls[0].arg.value.rules.singleProxy.port === 1080, 'port must be numeric');
assert(JSON.stringify(calls[0].arg.value.rules.bypassList) === JSON.stringify(['localhost']),
  'the bypass list must be honoured');
assert(calls[0].arg.scope === 'regular', 'scope must be regular');
assert(calls[1].api === 'webrtc' && calls[1].arg.value === 'disable_non_proxied_udp',
  'WebRTC must be restricted while proxied');
assert(applied.cleared === false && applied.webrtc === 'disable_non_proxied_udp',
  'the result must report what happened');

calls.length = 0;
const cleared = await applyNetwork(api, { proxy: null });
assert(calls[0].api === 'proxy.clear', 'a persona without a proxy must clear the setting');
assert(calls[0].arg.scope === 'regular', 'clear must be scoped to regular');
assert(calls[1].arg.value === 'default', 'the WebRTC policy must return to default');
assert(cleared.cleared === true, 'the result must report the clear');
assert(proxyConfig(null) === null, 'no proxy has no config');
assert(webrtcPolicy({ host: 'h', port: 1 }) === 'disable_non_proxied_udp', 'policy follows the proxy');

// A browser without these APIs must not throw: the persona still applies.
const bare = await applyNetwork({}, persona);
assert(bare.errors.length === 0 && bare.proxy === null, 'missing APIs must be tolerated');
console.log('ok');"""


@pytest.mark.skipif(shutil.which("node") is None, reason="node not installed")
def test_proxy_logic_executes_against_a_fake_chrome_api(tmp_path):
    """Executed evidence for the fixed_servers, WebRTC and clear paths."""
    (tmp_path / "network.mjs").write_text((EXTENSION / "src" / "network.js").read_text())
    (tmp_path / "proxy-harness.mjs").write_text(PROXY_HARNESS)
    result = subprocess.run(["node", str(tmp_path / "proxy-harness.mjs")],
                            capture_output=True, text=True)
    assert result.returncode == 0, result.stdout + result.stderr
    assert "ok" in result.stdout


def test_patch_overrides_location_and_network_surface():
    source = (EXTENSION / "src" / "patch.js").read_text()
    for token in ("getCurrentPosition", "watchPosition", "geolocation",
                  "effectiveType", "ScreenOrientation", "RTCPeerConnection",
                  "icecandidate", "onicecandidate"):
        assert token in source, token


def test_geo_mirror_matches_the_source_table():
    source = json.loads((REPO / "data" / "geo.json").read_text())
    mirror = json.loads((EXTENSION / "geo.json").read_text())
    assert mirror["cities"] == source["cities"]


def test_ip_is_shown_as_a_limit_not_a_setting():
    for relative in ("src/popup.html", "src/options.html"):
        html = (EXTENSION / relative).read_text().lower()
        assert "not spoofable" in html, relative


HARNESS = r"""import {
  derived, mergePersona, diffPersona, check, summarise, effectiveActive,
  rerollCandidates, nextInCycle, rotateSeeds, geoProblems, normaliseProxy,
  quickProxy, ipSummary, IP_NOTE, nextIdentity
} from './schema.mjs';

const assert = (ok, message) => { if (!ok) throw new Error(message); };

const base = {
  platform: 'windows', browser: 'chrome', version: '131',
  screenX: 1920, screenY: 1080, pixelRatio: 1,
  hardwareConcurrency: 8, deviceMemory: 8,
  touchPoints: 0, maxTouchPoints: 0,
  languagesZ: ['en-US', 'en'], timezone: 'America/New_York',
  ua: 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36',
  webglRenderer: 'ANGLE (NVIDIA, NVIDIA GeForce RTX 3060 Direct3D11 vs_5_0 ps_5_0, D3D11)',
  canvasSeed: 11, audioSeed: 22
};

// The bug this pins: with no `active` key in storage the worker resolved no
// persona and injected nothing, while the page still looked "spoofed" because
// the static script had applied the baked persona.
const catalogue = { default: 'a', personas: { a: base, b: { ...base } } };
assert(effectiveActive({ active: null }, catalogue) === 'a', 'a missing active must fall back to the default');
assert(effectiveActive({ active: 'b' }, catalogue) === 'b', 'an explicit active must win');
assert(effectiveActive({ active: 'deleted' }, catalogue) === 'a', 'a stale active must fall back to the default');
assert(effectiveActive({ active: null }, { default: null, personas: { z: base } }) === 'z', 'no default must fall back to the first persona');
assert(effectiveActive({}, { personas: {} }) === null, 'an empty mirror has no effective device');

assert(summarise(check(base)).level === 'ok', 'a generated Windows persona must be coherent');
assert(derived(base).availY === 1040, 'avail height must reserve the Windows chrome bar');

const merged = mergePersona(base, { deviceMemory: 16, languagesZ: ['de-DE', 'de'] });
assert(merged.deviceMemory === 16, 'an override must win over the baked value');
assert(merged.languagesZ[0] === 'de-DE', 'an ordered list must be replaced, not merged');

const patch = diffPersona(base, { ...base, deviceMemory: 16 });
assert(JSON.stringify(patch) === JSON.stringify({ deviceMemory: 16 }), 'diff must stay sparse: ' + JSON.stringify(patch));

// touchPoints is derived, not editable: a desktop override cannot survive, so
// the impossible "desktop with touch" state is unreachable rather than merely
// flagged. iOS is the mirror case and keeps the touch points it must report.
assert(mergePersona(base, { touchPoints: 5 }).touchPoints === 0, 'a desktop device must never report touch points');
assert(mergePersona({ ...base, platform: 'ios' }, { touchPoints: 0 }).touchPoints === 5, 'iOS must always report touch points');

const iosWild = check({ ...base, platform: 'ios', touchPoints: 5, maxTouchPoints: 5, pixelRatio: 3, hardwareConcurrency: 16, deviceMemory: 16 });
assert(iosWild.some((p) => p.field === 'hardwareConcurrency'), 'iOS core count must be checked');
assert(iosWild.some((p) => p.field === 'deviceMemory'), 'iOS memory must be checked');

const mismatch = check(mergePersona(base, { timezone: 'Asia/Tokyo' }));
assert(mismatch.some((p) => p.level === 'warn' && p.field === 'languages'), 'a timezone/language mismatch must warn');

const personas = { a: base, b: { ...base }, c: { ...base, platform: 'ios' } };
const pinned = rerollCandidates(personas, 'a', ['platform']);
assert(!pinned.includes('c'), 'a pinned OS must exclude other platforms');
assert(nextInCycle(['a', 'b'], 'a') === 'b', 'the cycle must advance');
assert(nextInCycle(['a', 'b'], 'b') === 'a', 'the cycle must wrap');
const rotated = rotateSeeds(base, 42);
assert(rotated.canvasSeed !== base.canvasSeed, 'seeds must rotate');
assert(rotated.ua === base.ua, 'rotating seeds must not touch identity');
const cities = {
  'Europe/Berlin': { latitude: 52.52, longitude: 13.405 },
  'Asia/Tokyo': { latitude: 35.6895, longitude: 139.6917 }
};
assert(geoProblems(cities, { ...base, timezone: 'Europe/Berlin', geo: { latitude: 52.5, longitude: 13.4 } }).length === 0,
  'coordinates in the zone city must be clean');
assert(geoProblems(cities, { ...base, timezone: 'Europe/Berlin', geo: { latitude: 35.68, longitude: 139.69 } })
  .some((p) => p.field === 'geo'), 'a coordinate far from its zone must warn');
assert(geoProblems(cities, { ...base, geo: { latitude: 91, longitude: 0 } })[0].level === 'error',
  'coordinates outside the earth must be an error');

const rejected = normaliseProxy({ scheme: 'gopher', host: '', port: 0 });
assert(rejected.error && rejected.proxy === null, 'an impossible proxy must be rejected');
const accepted = normaliseProxy({ scheme: 'SOCKS5', host: '127.0.0.1', port: 1080 });
assert(accepted.proxy.scheme === 'socks5' && accepted.proxy.port === 1080, 'a valid proxy must normalise');
assert(ipSummary({ ...base, proxy: accepted.proxy }).includes('socks5://127.0.0.1:1080'),
  'the IP row must name the proxy');
// The quick panel has no scheme field: editing the same endpoint keeps its
// scheme and credentials, but a new endpoint must not inherit either.
const withAuth = { ...accepted.proxy, username: 'alice', password: 's3cret' };
const sameTarget = quickProxy(withAuth, '127.0.0.1', 1080);
assert(sameTarget.proxy.scheme === 'socks5', 'the same proxy must keep its scheme');
assert(sameTarget.proxy.username === 'alice', 'the same proxy must keep its credentials');
const moved = quickProxy(withAuth, '10.0.0.5', 8080);
assert(moved.proxy.scheme === 'http', 'a new proxy target must not inherit socks5');
assert(moved.proxy.username === undefined, 'a new proxy target must not receive old credentials');
assert(ipSummary(base) === IP_NOTE, 'without a proxy the limit stays honest');
assert(derived(base).orientation.type === 'landscape-primary', 'orientation follows the screen');
assert(nextIdentity(['a', 'b'], 'a') === 'b', 'a whole roll must land on a different persona');
assert(nextIdentity(['a'], 'a') === 'a', 'a single persona cannot be rolled elsewhere');
console.log('ok');"""


@pytest.mark.skipif(shutil.which("node") is None, reason="node not installed")
def test_persona_composition_in_a_real_js_runtime(tmp_path):
    """The popup, editor and worker share schema.js; pin its behaviour."""
    (tmp_path / "schema.mjs").write_text((EXTENSION / "src" / "schema.js").read_text())
    (tmp_path / "harness.mjs").write_text(HARNESS)
    result = subprocess.run(["node", str(tmp_path / "harness.mjs")], capture_output=True, text=True)
    assert result.returncode == 0, result.stdout + result.stderr
    assert "ok" in result.stdout
