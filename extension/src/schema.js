export const CURRENT_SCHEMA = 2;
export const LOCKABLE = [
{ key: 'platform', label: 'OS' },
{ key: 'browser', label: 'Browser' },
{ key: 'screen', label: 'Screen' },
{ key: 'hardware', label: 'CPU' },
{ key: 'locale', label: 'Locale' },
{ key: 'gpu', label: 'GPU' },
{ key: 'noise', label: 'Noise' }
];
export const DEFAULTS = {
schemaVersion: CURRENT_SCHEMA,
enabled: true,
active: null,
locks: [],
imports: {},
overrides: {}
};
export const PLATFORM_LABEL = {
windows: 'Windows',
mac: 'macOS',
linux: 'Linux',
ios: 'iOS'
};
export const BROWSER_LABEL = {
chrome: 'Chrome',
edge: 'Edge',
safari: 'Safari'
};
const TZ_LANGUAGE = {
'Europe/Berlin': ['de'], 'Europe/Vienna': ['de'], 'Europe/Zurich': ['de'],
'Europe/London': ['en'], 'Europe/Dublin': ['en'],
'Europe/Paris': ['fr'], 'Europe/Madrid': ['es'], 'Europe/Rome': ['it'],
'Europe/Amsterdam': ['nl'], 'Europe/Stockholm': ['sv'], 'Europe/Warsaw': ['pl'],
'Europe/Lisbon': ['pt'], 'Europe/Prague': ['cs'], 'Europe/Helsinki': ['fi'],
'America/New_York': ['en'], 'America/Chicago': ['en'], 'America/Denver': ['en'],
'America/Los_Angeles': ['en'], 'America/Toronto': ['en'], 'America/Vancouver': ['en'],
'America/Sao_Paulo': ['pt'], 'America/Mexico_City': ['es'], 'America/Bogota': ['es'],
'Asia/Tokyo': ['ja'], 'Asia/Seoul': ['ko'], 'Asia/Shanghai': ['zh'],
'Asia/Hong_Kong': ['zh'], 'Asia/Taipei': ['zh'], 'Asia/Singapore': ['en'],
'Asia/Kolkata': ['en'], 'Asia/Dubai': ['ar'], 'Asia/Jakarta': ['id'],
'Australia/Sydney': ['en'], 'Pacific/Auckland': ['en'],
'Africa/Johannesburg': ['en'], 'Africa/Cairo': ['ar'], 'Africa/Lagos': ['en'],
'UTC': []
};
export const GEO_TOLERANCE_KM = 250;
export function distanceKm(a, b) {
const rad = (value) => (value * Math.PI) / 180;
const dLat = rad(b.latitude - a.latitude);
const dLon = rad(b.longitude - a.longitude);
const h = Math.sin(dLat / 2) ** 2 +
Math.cos(rad(a.latitude)) * Math.cos(rad(b.latitude)) * Math.sin(dLon / 2) ** 2;
return 2 * 6371.0088 * Math.asin(Math.min(1, Math.sqrt(h)));
}
export function nearestCity(cities, latitude, longitude) {
if (!cities || !isFinite(latitude) || !isFinite(longitude)) return null;
let best = null;
for (const [timezone, entry] of Object.entries(cities)) {
if (!entry || typeof entry.latitude !== 'number') continue;
const distance = distanceKm({ latitude, longitude }, entry);
if (!best || distance < best.distance) best = { timezone, entry, distance };
}
return best;
}
export function geoProblems(cities, persona) {
const geo = persona && persona.geo;
if (!geo) return [];
const out = [];
const latitude = Number(geo.latitude);
const longitude = Number(geo.longitude);
if (!isFinite(latitude) || !isFinite(longitude) ||
latitude < -90 || latitude > 90 || longitude < -180 || longitude > 180) {
out.push({ level: 'error', field: 'geo', message: 'coordinates are outside the earth' });
return out;
}
const home = cities && cities[persona.timezone];
if (!home) return out;
const span = distanceKm({ latitude, longitude }, home);
if (span > GEO_TOLERANCE_KM) {
out.push({
level: 'warn',
field: 'geo',
message: Math.round(span) + ' km from ' + (home.city || persona.timezone) +
' (' + persona.timezone + ')'
});
}
return out;
}
export function normaliseProxy(input) {
if (!input) return { proxy: null, error: null };
const mode = String(input.mode || 'fixed_servers').toLowerCase();
if (mode === 'system' || mode === 'direct') return { proxy: { mode }, error: null };
if (mode !== 'fixed_servers') {
return { proxy: null, error: 'mode must be system, direct or fixed_servers' };
}
const scheme = String(input.scheme || 'http').toLowerCase();
const host = String(input.host || '').trim();
const port = Number(input.port);
if (!['http', 'https', 'socks4', 'socks5'].includes(scheme)) {
return { proxy: null, error: 'scheme must be http, https, socks4 or socks5' };
}
if (!host || /\s/.test(host) || host.includes('/')) {
return { proxy: null, error: 'host is required and must not contain spaces' };
}
if (!Number.isInteger(port) || port < 1 || port > 65535) {
return { proxy: null, error: 'port must be an integer between 1 and 65535' };
}
const bypass = Array.isArray(input.bypass) && input.bypass.length
? input.bypass.slice()
: ['localhost', '127.0.0.1'];
const proxy = { mode: 'fixed_servers', scheme, host, port, bypass };
if (input.username != null) {
if (!String(input.username).trim()) {
return { proxy: null, error: 'username is empty' };
}
proxy.username = String(input.username);
proxy.password = String(input.password == null ? '' : input.password);
}
return { proxy, error: null };
}
export function quickProxy(previous, host, port) {
const same = !!previous && String(previous.host || '') === String(host) &&
Number(previous.port) === Number(port);
const input = {
mode: 'fixed_servers',
scheme: same && previous.scheme ? previous.scheme : 'http',
host,
port
};
if (same) {
if (Array.isArray(previous.bypass) && previous.bypass.length) input.bypass = previous.bypass;
if (previous.username != null) {
input.username = previous.username;
input.password = previous.password;
}
}
return normaliseProxy(input);
}
export function parseProxyUrl(text) {
const raw = String(text || '').trim();
if (!raw) return { proxy: null, error: 'paste a proxy URL or host:port' };
let scheme = 'http';
let host = '';
let port = null;
let username = null;
let password = null;
if (raw.includes('://')) {
let parsed = null;
try {
parsed = new URL(raw);
} catch (error) {
return { proxy: null, error: 'not a proxy URL' };
}
scheme = String(parsed.protocol || 'http:').replace(':', '').toLowerCase();
host = parsed.hostname || '';
port = parsed.port ? Number(parsed.port) : null;
username = parsed.username ? decodeURIComponent(parsed.username) : null;
password = parsed.password ? decodeURIComponent(parsed.password) : null;
} else {
const match = /^(?:\[([^\]]+)\]|([^:/]+)):(\d{1,5})$/.exec(raw);
if (!match) return { proxy: null, error: 'expected host:port or scheme://[user:pass@]host:port' };
host = match[1] || match[2];
port = Number(match[3]);
}
if (scheme === 'socks5h' || scheme === 'socks') scheme = 'socks5';
if (port == null) return { proxy: null, error: 'the URL has no port' };
return normaliseProxy({ scheme, host, port, username, password });
}
export function ipSummary(persona) {
const proxy = persona && persona.proxy;
if (!proxy) return IP_NOTE;
const mode = String(proxy.mode || 'fixed_servers').toLowerCase();
if (mode === 'system') return 'system / VPN \u00b7 follows your OS route';
if (mode === 'direct') return 'direct \u00b7 system proxy ignored';
return 'via ' + proxy.scheme + '://' + proxy.host + ':' + proxy.port +
(proxy.username ? ' (auth)' : '') + ' \u00b7 WebRTC blocked';
}
function isPlainObject(value) {
return !!value && typeof value === 'object' && !Array.isArray(value);
}
export async function readState() {
const raw = (await chrome.storage.local.get(null)) || {};
const state = {
...DEFAULTS,
...raw,
locks: Array.isArray(raw.locks) ? raw.locks : [],
imports: isPlainObject(raw.imports) ? raw.imports : {},
overrides: isPlainObject(raw.overrides) ? raw.overrides : {}
};
if (raw.schemaVersion !== CURRENT_SCHEMA) {
await chrome.storage.local.set({
schemaVersion: CURRENT_SCHEMA,
enabled: state.enabled !== false,
active: state.active || null,
locks: state.locks,
overrides: state.overrides
});
}
return state;
}
export function effectiveActive(state, mirror) {
const personas = (mirror && mirror.personas) || {};
if (state && state.active && personas[state.active]) return state.active;
if (mirror && mirror.default && personas[mirror.default]) return mirror.default;
return Object.keys(personas)[0] || null;
}
export function parseImport(text) {
let parsed;
try {
parsed = JSON.parse(String(text || ''));
} catch (error) {
return { personas: {}, error: 'not valid JSON' };
}
if (parsed && typeof parsed === 'object' && parsed.persona && typeof parsed.persona === 'object') {
parsed = parsed.persona;
}
if (Array.isArray(parsed)) {
if (!parsed.length) return { personas: {}, error: 'the array is empty' };
const personas = {};
parsed.forEach((entry, index) => { personas['imported-' + (index + 1)] = entry; });
return { personas, error: null };
}
if (!parsed || typeof parsed !== 'object') {
return { personas: {}, error: 'expected a persona object or {personas: {...}}' };
}
if (parsed.personas && typeof parsed.personas === 'object') {
const personas = {};
for (const [name, persona] of Object.entries(parsed.personas)) {
personas[name] = persona;
}
if (!Object.keys(personas).length) return { personas: {}, error: 'the bundle has no personas' };
return { personas, error: null };
}
return { personas: { imported: parsed }, error: null };
}
export function derived(persona) {
if (!persona) return null;
const p = { ...persona };
const ios = p.platform === 'ios';
p.maxTouchPoints = ios ? (p.maxTouchPoints || 5) : 0;
p.touchPoints = p.maxTouchPoints;
const chromeBar = ios ? 0 : p.platform === 'windows' ? 40 : p.platform === 'mac' ? 25 : 24;
p.availX = p.screenX;
p.availY = Math.max(1, p.screenY - chromeBar);
if (ios && p.deviceMemory != null) p.deviceMemory = Math.min(p.deviceMemory, 8);
p.orientation = {
type: p.screenX >= p.screenY ? 'landscape-primary' : 'portrait-primary',
angle: 0
};
return p;
}
export function mergePersona(base, patch) {
if (!base) return null;
if (!patch) return derived(base);
const out = { ...base };
for (const [key, value] of Object.entries(patch)) {
out[key] = isPlainObject(value) && isPlainObject(base[key])
? { ...base[key], ...value }
: value;
}
return derived(out);
}
export function diffPersona(base, edited) {
const patch = {};
if (!base || !edited) return patch;
for (const key of Object.keys(edited)) {
if (key === 'availX' || key === 'availY' || key === 'touchPoints' || key === 'orientation') continue; // derived
const before = base[key];
const after = edited[key];
if (isPlainObject(after)) {
if (JSON.stringify(before) !== JSON.stringify(after)) patch[key] = after;
} else if (JSON.stringify(before) !== JSON.stringify(after)) {
patch[key] = after;
}
}
return patch;
}
export function check(persona, cities) {
if (!persona) return [{ level: 'error', field: 'persona', message: 'no persona selected' }];
const out = [];
const add = (level, field, message) => out.push({ level, field, message });
const ios = persona.platform === 'ios';
if (ios && persona.deviceMemory != null && persona.deviceMemory > 8) {
add('error', 'deviceMemory', 'no iOS device reports more than 8 GB');
}
if (ios && persona.hardwareConcurrency > 8) {
add('error', 'hardwareConcurrency', 'no iOS device reports more than 8 cores');
}
if (ios && !(persona.touchPoints > 0)) {
add('error', 'touchPoints', 'an iOS device must report touch points');
}
if (!ios && persona.touchPoints > 0) {
add('error', 'touchPoints', 'a desktop device reports zero touch points');
}
if (!ios && persona.pixelRatio > 2) {
add('error', 'pixelRatio', 'no desktop display ships above 2x');
}
if (persona.screenX < 320 || persona.screenY < 320) {
add('error', 'screenX', 'no real screen is that small');
}
if (persona.hardwareConcurrency < 2) {
add('error', 'hardwareConcurrency', 'at least 2 cores are reported by every browser');
}
const language = ((persona.languagesZ || [])[0] || '').toLowerCase();
const primary = language.split('-')[0];
const expected = TZ_LANGUAGE[persona.timezone];
if (primary && expected && expected.length && !expected.includes(primary)) {
add('warn', 'languages', 'language ' + language + ' does not match ' + persona.timezone);
}
if (ios && persona.pixelRatio < 2) {
add('warn', 'pixelRatio', 'every iOS device is retina (2x or 3x)');
}
if (persona.deviceMemory != null && persona.hardwareConcurrency >= 12 && persona.deviceMemory < 8) {
add('warn', 'deviceMemory', 'many cores but little memory is unusual');
}
if (persona.webglRenderer && /swiftshader|llvmpipe|software/i.test(persona.webglRenderer)) {
add('warn', 'webglRenderer', 'a software renderer is itself a bot signal');
}
for (const problem of geoProblems(cities, persona)) out.push(problem);
if (persona.proxy) {
const { error } = normaliseProxy(persona.proxy);
if (error) add('error', 'proxy', error);
}
return out;
}
export function summarise(problems) {
const errors = problems.filter((p) => p.level === 'error').length;
const warns = problems.filter((p) => p.level === 'warn').length;
if (errors) return { level: 'error', errors, warns, text: errors + ' error' + (errors === 1 ? '' : 's') };
if (warns) return { level: 'warn', errors, warns, text: warns + ' warning' + (warns === 1 ? '' : 's') };
return { level: 'ok', errors: 0, warns: 0, text: 'coherent' };
}
export function rerollCandidates(personas, active, locks) {
const names = Object.keys(personas || {});
const current = personas && personas[active];
if (!current) return names;
const pinned = new Set(locks || []);
const matched = names.filter((name) => {
const p = personas[name];
if (!p) return false;
if (pinned.has('platform') && p.platform !== current.platform) return false;
if (pinned.has('browser') && p.browser !== current.browser) return false;
return true;
});
return matched.length ? matched : names;
}
export function nextIdentity(names, active) {
return nextInCycle(names, active);
}
export function nextInCycle(names, active) {
if (!names || !names.length) return null;
const index = names.indexOf(active);
if (index < 0) return names[0];
return names[(index + 1) % names.length];
}
export function rotateSeeds(persona, salt) {
const base = (salt == null ? Date.now() : salt) >>> 0;
const mix = (seed) => {
let x = ((seed >>> 0) ^ base) >>> 0;
x ^= x << 13; x >>>= 0;
x ^= x >> 17;
x ^= x << 5; x >>>= 0;
return x >>> 0;
};
return {
...persona,
canvasSeed: mix(persona.canvasSeed || 1),
audioSeed: mix(persona.audioSeed || 2)
};
}
export function describeDevice(persona) {
if (!persona) return 'no persona';
const os = PLATFORM_LABEL[persona.platform] || persona.platform || '?';
const browser = BROWSER_LABEL[persona.browser] || persona.browser || '?';
return os + ' \u00b7 ' + browser + (persona.version ? ' ' + persona.version : '');
}
export function describeScreen(persona) {
if (!persona) return '-';
return persona.screenX + '\u00d7' + persona.screenY + ' @' + persona.pixelRatio + 'x';
}
export function shortUa(persona) {
if (!persona || !persona.ua) return '-';
const match = /(Chrome|Safari|Edg|Version)\/[\d.]+/.exec(persona.ua);
const tail = match ? match[0] : persona.ua.slice(-28);
const os = /\(([^)]+)\)/.exec(persona.ua);
return (os ? os[1].split(';')[0].trim() + ' \u00b7 ' : '') + tail;
}
export function shortGpu(persona) {
if (!persona || !persona.webglRenderer) return '-';
const nested = /^ANGLE \([^,]+, (.*), [^,]+\)$/.exec(persona.webglRenderer);
if (nested) return nested[1].trim();
const inside = /\(([^)]*)\)/.exec(persona.webglRenderer);
return inside ? inside[1].split(',').slice(-1)[0].trim() : persona.webglRenderer;
}
export const IP_NOTE = 'not spoofable \u2014 needs a proxy or VPN';
