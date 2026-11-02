import {
readState,
mergePersona,
derived,
check,
summarise,
diffPersona,
rotateSeeds,
LOCKABLE,
PLATFORM_LABEL,
BROWSER_LABEL,
nearestCity,
normaliseProxy,
parseProxyUrl,
ipSummary
} from './schema.js';
const el = (id) => document.getElementById(id);
const send = (message) => new Promise((resolve) => chrome.runtime.sendMessage(message, (r) => resolve(r || {})));
const DPR_CHOICES = [1, 1.25, 1.5, 2, 3];
const CORE_CHOICES = [2, 4, 6, 8, 12, 16];
const MEMORY_CHOICES = [4, 8, 16, 32, null];
let mirror = { personas: {} };
let cities = null;
let state = null;
let name = null;
let draft = null;
const baked = () => mirror.personas[name] || null;
const savedPatch = () => (state.overrides || {})[name] || {};
function option(value, label) {
const node = document.createElement('option');
node.value = value == null ? '' : String(value);
node.textContent = label;
return node;
}
function fillSelect(node, choices) {
const previous = node.value;
node.innerHTML = '';
for (const choice of choices) {
node.appendChild(option(choice.value, choice.label));
}
if (previous) node.value = previous;
}
function unique(values) {
const out = [];
for (const value of values) if (value != null && !out.includes(value)) out.push(value);
return out;
}
function renderDevices() {
const list = el('devices');
list.innerHTML = '';
const names = Object.keys(mirror.personas);
if (!names.length) {
const note = document.createElement('p');
note.className = 'rail-note';
note.textContent = 'No devices yet — run: fps gen';
list.appendChild(note);
return;
}
for (const id of names) {
const persona = mirror.personas[id];
const button = document.createElement('button');
button.type = 'button';
button.className = 'device';
button.setAttribute('aria-current', id === name ? 'true' : 'false');
button.textContent = (PLATFORM_LABEL[persona.platform] || persona.platform) + ' \u00b7 ' +
(BROWSER_LABEL[persona.browser] || persona.browser);
const small = document.createElement('small');
const customised = (state.overrides || {})[id];
small.textContent = (customised ? 'customised \u00b7 ' : '') + id;
button.appendChild(small);
button.addEventListener('click', () => pick(id));
list.appendChild(button);
}
}
function renderLocks() {
const box = el('locks');
box.innerHTML = '';
const pinned = new Set(state.locks || []);
for (const item of LOCKABLE) {
const chip = document.createElement('button');
chip.type = 'button';
chip.className = 'chip';
chip.textContent = item.label;
chip.setAttribute('aria-pressed', pinned.has(item.key) ? 'true' : 'false');
chip.addEventListener('click', () => toggleLock(item.key));
box.appendChild(chip);
}
}
function renderPins() {
const pinned = new Set(state.locks || []);
document.querySelectorAll('[data-lock]').forEach((button) => {
const on = pinned.has(button.dataset.lock);
button.setAttribute('aria-pressed', on ? 'true' : 'false');
button.textContent = on ? 'Pinned' : 'Pin';
});
}
async function toggleLock(key) {
const next = new Set(state.locks || []);
if (next.has(key)) next.delete(key);
else next.add(key);
const response = await send({ type: 'setState', patch: { locks: [...next] } });
state = { ...state, ...(response.state || {}) };
renderLocks();
renderPins();
setStatus(next.has(key) ? 'Pinned ' + key + ' \u2014 rerolls will keep it.' : 'Unpinned ' + key + '.');
}
function renderLanguages() {
const list = el('languages');
list.innerHTML = '';
const languages = draft.languagesZ || [];
languages.forEach((tag, index) => {
const item = document.createElement('li');
const label = document.createElement('button');
label.type = 'button';
label.className = 'tag-button';
label.textContent = tag;
if (index > 0) {
label.title = 'Make ' + tag + ' the primary language';
label.addEventListener('click', () => {
update('languagesZ', [tag, ...languages.filter((other) => other !== tag)]);
renderLanguages();
});
} else {
label.title = 'Primary language \u2014 sent as navigator.language';
label.disabled = true;
}
item.appendChild(label);
if (index === 0) {
const mark = document.createElement('span');
mark.className = 'primary-mark';
mark.textContent = 'primary';
item.appendChild(mark);
}
const remove = document.createElement('button');
remove.type = 'button';
remove.className = 'remove';
remove.textContent = '\u00d7';
remove.setAttribute('aria-label', 'Remove ' + tag);
remove.addEventListener('click', () => {
update('languagesZ', languages.filter((_, i) => i !== index));
renderLanguages();
});
item.appendChild(remove);
list.appendChild(item);
});
}
function renderTimezoneOptions() {
const node = el('timezone');
let zones = [];
try {
zones = typeof Intl.supportedValuesOf === 'function' ? Intl.supportedValuesOf('timeZone') : [];
} catch (error) {
zones = [];
}
if (!zones.length) zones = [draft.timezone || 'UTC'];
if (draft.timezone && !zones.includes(draft.timezone)) zones = [draft.timezone, ...zones];
node.innerHTML = '';
for (const zone of zones) node.appendChild(option(zone, zone));
}
function renderScreenOptions() {
const node = el('screen');
const combos = unique(Object.values(mirror.personas).map((p) => p.screenX + 'x' + p.screenY));
node.innerHTML = '';
for (const combo of combos) node.appendChild(option(combo, combo.replace('x', ' \u00d7 ')));
node.appendChild(option('custom', 'custom\u2026'));
const current = draft.screenX + 'x' + draft.screenY;
node.value = combos.includes(current) ? current : 'custom';
}
function renderGpuOptions() {
const node = el('webglRenderer');
const platform = draft.platform;
const sameOs = Object.values(mirror.personas)
.filter((p) => p.platform === platform && p.webglRenderer)
.map((p) => p.webglRenderer);
const choices = unique([draft.webglRenderer, ...sameOs]);
node.innerHTML = '';
for (const renderer of choices) node.appendChild(option(renderer, renderer));
}
function renderMemoryOptions() {
const ios = draft.platform === 'ios';
const choices = ios ? MEMORY_CHOICES.filter((m) => m != null && m <= 8) : MEMORY_CHOICES;
const node = el('deviceMemory');
node.innerHTML = '';
for (const value of choices) {
node.appendChild(option(value == null ? '' : value, value == null ? 'not reported' : value + ' GB'));
}
node.value = draft.deviceMemory == null ? '' : String(draft.deviceMemory);
}
function renderPlaceOptions() {
const node = el('geo-place');
node.innerHTML = '';
if (!cities) {
node.appendChild(option('', 'location table unavailable \u2014 run: fps gen'));
node.disabled = true;
return;
}
node.disabled = false;
const entries = Object.entries(cities)
.filter(([, entry]) => entry && entry.city)
.sort((a, b) => String(a[1].city).localeCompare(String(b[1].city)));
for (const [timezone, entry] of entries) {
node.appendChild(option(timezone, entry.city + (entry.country ? ', ' + entry.country : '') +
' \u2014 ' + timezone));
}
if (draft.timezone) node.value = draft.timezone;
}
function renderGeo() {
const geo = draft.geo || {};
el('geo-lat').value = geo.latitude == null ? '' : geo.latitude;
el('geo-lon').value = geo.longitude == null ? '' : geo.longitude;
const near = nearestCity(cities, Number(geo.latitude), Number(geo.longitude));
let label = geo.city ? geo.city + (geo.country ? ', ' + geo.country : '') : '-';
if (near && near.timezone !== draft.timezone) {
label += ' \u00b7 ' + Math.round(near.distance) + ' km from ' + near.timezone;
}
el('geo-city').textContent = label;
if (cities && draft.timezone) el('geo-place').value = draft.timezone;
const problems = check(draft, cities).filter((problem) => problem.field === 'geo');
if (problems.length) {
el('geo-status').className = 'note warn-text';
el('geo-status').textContent = problems[0].message + ' \u2014 flagged, not blocked.';
} else if (geo.city) {
el('geo-status').className = 'note';
el('geo-status').textContent = 'Coordinates match ' + geo.city + ' in ' + draft.timezone + '.';
} else {
el('geo-status').className = 'note';
el('geo-status').textContent = 'No coordinates set.';
}
}
function describeProxy(proxy) {
if (!proxy) return 'none \u2014 your real egress IP';
const mode = String(proxy.mode || 'fixed_servers');
if (mode === 'system') return 'system / VPN \u2014 no proxy configured';
if (mode === 'direct') return 'direct \u2014 system proxy ignored';
return proxy.scheme + '://' + proxy.host + ':' + proxy.port +
(proxy.username ? ' (auth)' : '');
}
function renderProxy() {
const proxy = draft.proxy || null;
const mode = proxy ? String(proxy.mode || 'fixed_servers') : 'system';
el('proxy-mode').value = mode;
el('proxy-scheme').value = proxy && proxy.scheme ? proxy.scheme : 'http';
el('proxy-host').value = proxy && proxy.host ? proxy.host : '';
el('proxy-port').value = proxy && proxy.port ? proxy.port : '';
el('proxy-username').value = proxy && proxy.username ? proxy.username : '';
el('proxy-password').value = proxy && proxy.password ? proxy.password : '';
el('ro-ip').textContent = ipSummary(draft);
el('ro-proxy').textContent = describeProxy(proxy);
el('ro-bypass').textContent = proxy && proxy.bypass && proxy.bypass.length
? proxy.bypass.join(', ')
: '\u2014';
el('ro-launch').textContent = proxy && String(proxy.mode || 'fixed_servers') === 'fixed_servers'
? 'fps launch ' + (name || 'NAME') + ' --proxy ' + proxy.scheme + '://' + proxy.host + ':' + proxy.port
: 'fps launch ' + (name || 'NAME');
el('ro-webrtc').textContent = proxy
? 'restricted to the proxied path \u2014 no host candidates'
: 'host candidates filtered \u2014 no local IP leak';
}
function renderForm() {
if (!draft) return;
renderTimezoneOptions();
el('timezone').value = draft.timezone || 'UTC';
renderPlaceOptions();
const addChoices = unique([...(draft.languagesZ || []), 'en-US', 'en-GB', 'de-DE', 'fr-FR', 'es-ES', 'ja-JP', 'zh-CN']);
el('language-add').innerHTML = '';
for (const tag of addChoices) el('language-add').appendChild(option(tag, tag));
renderLanguages();
renderScreenOptions();
el('screenX').value = draft.screenX;
el('screenY').value = draft.screenY;
const dpr = el('pixelRatio');
dpr.innerHTML = '';
for (const value of DPR_CHOICES) dpr.appendChild(option(value, value + '\u00d7'));
dpr.value = String(draft.pixelRatio);
const cores = el('hardwareConcurrency');
cores.innerHTML = '';
for (const value of CORE_CHOICES) cores.appendChild(option(value, value + ' cores'));
cores.value = String(draft.hardwareConcurrency);
renderMemoryOptions();
renderGpuOptions();
el('webglRenderer').value = draft.webglRenderer || '';
el('webglRenderer').title = draft.webglRenderer || '';
el('canvasSeed').value = draft.canvasSeed == null ? '' : draft.canvasSeed;
el('audioSeed').value = draft.audioSeed == null ? '' : draft.audioSeed;
refresh();
}
function refresh() {
if (!draft) return;
el('ro-ua').textContent = draft.ua || '-';
const brands = ((draft.userAgentData || {}).brands || [])
.map((b) => b.brand + ' ' + b.version).join(', ');
el('ro-brands').textContent = brands || '-';
el('ro-platform').textContent = (draft.platformKey || draft.platform || '-') +
(draft.userAgentData && draft.userAgentData.platformVersion
? ' \u00b7 platformVersion ' + draft.userAgentData.platformVersion : '');
el('ro-touch').textContent = String(draft.touchPoints == null ? 0 : draft.touchPoints);
el('ro-avail').textContent = draft.availX + ' \u00d7 ' + draft.availY;
const problems = check(draft, cities);
const verdict = summarise(problems);
const hits = problems.filter((p) => p.level !== 'ok');
const banner = el('banner');
const editable = !!(state.overrides || {})[name];
if (verdict.level === 'error') {
banner.className = 'banner error';
banner.textContent = verdict.text + ' \u2014 a real browser cannot report this. Fix before saving.';
} else if (verdict.level === 'warn') {
banner.className = 'banner warn';
banner.textContent = verdict.text + ' \u2014 allowed, but a detector may notice.';
} else {
banner.className = 'banner ok';
banner.textContent = editable
? 'Coherent. Customised over the baked persona.'
: 'Coherent \u2014 exactly as generated.';
}
const list = el('checks');
list.innerHTML = '';
if (!hits.length) {
const item = document.createElement('li');
item.className = 'ok';
item.textContent = 'No contradictions between OS, screen, hardware, locale and GPU';
list.appendChild(item);
}
for (const problem of hits) {
const item = document.createElement('li');
item.className = problem.level;
item.textContent = problem.field + ': ' + problem.message;
list.appendChild(item);
}
el('coherence-count').textContent = verdict.level === 'ok' ? 'none' : verdict.text;
const patches = (state.overrides || {})[name] || {};
const patchCount = Object.keys(patches).length;
el('ap-name').textContent = name || '-';
el('ap-seeds').textContent = draft.canvasSeed + ' / ' + draft.audioSeed;
el('ap-overrides').textContent = patchCount
? patchCount + ' field' + (patchCount === 1 ? '' : 's') + ' over the baked persona'
: 'none \u2014 exactly as generated';
el('ap-egress').textContent = draft.proxy
? draft.proxy.scheme + '://' + draft.proxy.host + ':' + draft.proxy.port + ' (via proxy)'
: 'real egress IP (no proxy)';
renderGeo();
renderProxy();
el('save').disabled = verdict.level === 'error';
}
function update(key, value) {
draft = derived({ ...draft, [key]: value });
if (key === 'deviceMemory') renderMemoryOptions();
refresh();
}
function pick(id) {
name = id;
draft = mergePersona(baked(), savedPatch());
renderDevices();
renderForm();
setStatus('');
}
const SHUFFLE_GROUPS = {
screen: ['screenX', 'screenY', 'pixelRatio'],
hardware: ['hardwareConcurrency', 'deviceMemory'],
gpu: ['webglRenderer']
};
function setRandomize(text) {
const node = el('randomize-status');
if (node) node.textContent = text;
setStatus(text);
}
function applyShuffle(groups) {
if (!draft) return;
const pinned = new Set(state.locks || []);
const wanted = groups.filter((group) => !pinned.has(group));
if (!wanted.length) {
setRandomize('Those sections are pinned \u2014 unpin one to shuffle it.');
return;
}
let source = null;
if (wanted.some((group) => group !== 'noise')) {
const same = Object.entries(mirror.personas)
.filter(([id, p]) => id !== name && p.platform === draft.platform);
const pool = same.length ? same : Object.entries(mirror.personas).filter(([id]) => id !== name);
if (!pool.length) {
setRandomize('Only one persona \u2014 run: fps gen for more.');
return;
}
source = pool[Math.floor(Math.random() * pool.length)][1];
}
let next = { ...draft };
for (const group of wanted) {
if (group === 'noise') {
next = rotateSeeds(next);
continue;
}
for (const field of SHUFFLE_GROUPS[group]) {
if (source[field] !== undefined) next[field] = source[field];
}
}
draft = derived(next);
renderForm();
setRandomize('Shuffled ' + wanted.join(', ') + '. Not saved until you press Save.');
}
async function persist(patch) {
const response = await send({ type: 'setState', patch });
state = { ...state, ...(response.state || {}) };
return response;
}
function setStatus(text) {
el('status').textContent = text;
}
el('timezone').addEventListener('change', (event) => update('timezone', event.target.value));
el('language-push').addEventListener('click', () => {
const tag = el('language-add').value;
const languages = draft.languagesZ || [];
if (!tag || languages.includes(tag)) return;
update('languagesZ', [...languages, tag]);
renderLanguages();
});
el('screen').addEventListener('change', (event) => {
if (event.target.value === 'custom') return;
const [width, height] = event.target.value.split('x').map(Number);
draft = derived({ ...draft, screenX: width, screenY: height });
el('screenX').value = width;
el('screenY').value = height;
refresh();
});
el('screenX').addEventListener('change', (event) => update('screenX', Number(event.target.value) || 320));
el('screenY').addEventListener('change', (event) => update('screenY', Number(event.target.value) || 320));
el('pixelRatio').addEventListener('change', (event) => update('pixelRatio', Number(event.target.value)));
el('hardwareConcurrency').addEventListener('change', (event) => update('hardwareConcurrency', Number(event.target.value)));
el('deviceMemory').addEventListener('change', (event) => {
const raw = event.target.value;
update('deviceMemory', raw === '' ? null : Number(raw));
});
el('webglRenderer').addEventListener('change', (event) => update('webglRenderer', event.target.value));
el('canvasSeed').addEventListener('change', (event) => update('canvasSeed', Number(event.target.value) || 1));
el('audioSeed').addEventListener('change', (event) => update('audioSeed', Number(event.target.value) || 2));
function applyGeo(latitude, longitude) {
const accuracy = (draft.geo && draft.geo.accuracy) || 50;
update('geo', { ...(draft.geo || {}), latitude, longitude, accuracy });
}
el('geo-lat').addEventListener('change', (event) => {
applyGeo(Number(event.target.value), Number((draft.geo || {}).longitude));
});
el('geo-lon').addEventListener('change', (event) => {
applyGeo(Number((draft.geo || {}).latitude), Number(event.target.value));
});
el('geo-place').addEventListener('change', (event) => {
const zone = event.target.value;
const entry = cities && cities[zone];
if (!entry) return;
draft = derived({ ...draft, timezone: zone, geo: { ...entry } });
el('timezone').value = zone;
renderGeo();
refresh();
setStatus('Location set to ' + entry.city + ' (' + zone + ') \u2014 coordinates moved with it.');
});
el('geo-snap').addEventListener('click', () => {
const geo = draft.geo || {};
const near = nearestCity(cities, Number(geo.latitude), Number(geo.longitude));
if (!near) {
setStatus('No location table loaded \u2014 run: fps gen, then reload this page.');
return;
}
draft = derived({
...draft,
timezone: near.timezone,
geo: { ...near.entry, accuracy: geo.accuracy || near.entry.accuracy }
});
el('timezone').value = near.timezone;
renderGeo();
refresh();
setStatus('Snapped to ' + near.entry.city + ' (' + near.timezone + ').');
});
el('proxy-mode').addEventListener('change', () => {
const mode = el('proxy-mode').value;
if (mode === 'fixed_servers') {
setStatus('Fill in the proxy fields or paste a provider URL, then save.');
return;
}
update('proxy', { mode });
setStatus(mode === 'direct'
? 'Direct routing saved \u2014 Chrome ignores the system proxy.'
: 'System routing saved \u2014 an OS-level VPN now applies.');
});
el('proxy-paste').addEventListener('click', () => {
const result = parseProxyUrl(el('proxy-url').value);
if (result.error) {
setStatus('Proxy URL: ' + result.error);
return;
}
update('proxy', result.proxy);
el('proxy-url').value = '';
setStatus('Proxy saved from URL \u2014 credentials stay in this browser profile.');
});
el('proxy-apply').addEventListener('click', () => {
const result = normaliseProxy({
scheme: el('proxy-scheme').value,
host: el('proxy-host').value,
port: Number(el('proxy-port').value),
username: el('proxy-username').value || null,
password: el('proxy-password').value
});
if (result.error) {
setStatus('Proxy: ' + result.error);
return;
}
update('proxy', result.proxy);
setStatus('Proxy saved \u2014 the IP row now names it. Reload pages to re-route them.');
});
el('proxy-clear').addEventListener('click', () => {
update('proxy', { mode: 'system' });
setStatus('System routing \u2014 your OS route, including any VPN, applies.');
});
el('canvas-dice').addEventListener('click', () => {
draft = rotateSeeds(draft);
el('canvasSeed').value = draft.canvasSeed;
el('audioSeed').value = draft.audioSeed;
refresh();
});
el('audio-dice').addEventListener('click', () => {
draft = rotateSeeds(draft);
el('canvasSeed').value = draft.canvasSeed;
el('audioSeed').value = draft.audioSeed;
refresh();
});
el('save').addEventListener('click', async () => {
if (!name) return;
const patch = diffPersona(baked(), draft);
const overrides = { ...(state.overrides || {}) };
if (Object.keys(patch).length) overrides[name] = patch;
else delete overrides[name];
await persist({ overrides });
renderDevices();
renderForm();
chrome.tabs.query({ url: ['http://*/*', 'https://*/*'] }, (tabs) => {
const count = (tabs || []).length;
const saved = Object.keys(patch).length
? 'Saved. '
: 'Saved \u2014 this device matches the generated persona. ';
setStatus(saved + (count
? 'Reload your ' + count + ' open http(s) tab to apply the JavaScript side.'
: 'JavaScript patches apply on the next page load; headers are already live.'));
});
});
el('reset-persona').addEventListener('click', async () => {
const overrides = { ...(state.overrides || {}) };
delete overrides[name];
await persist({ overrides });
pick(name);
setStatus('Reverted ' + name + ' to the generated persona.');
});
el('reset-all').addEventListener('click', async () => {
await persist({ overrides: {}, locks: [] });
renderLocks();
renderPins();
pick(name);
setStatus('Removed all edits and pins.');
});
document.querySelectorAll('[data-lock]').forEach((button) => {
button.addEventListener('click', () => toggleLock(button.dataset.lock));
});
el('reroll-fields').addEventListener('click', () => applyShuffle(['screen', 'hardware', 'gpu', 'noise']));
el('shuffle-screen').addEventListener('click', () => applyShuffle(['screen']));
el('shuffle-hardware').addEventListener('click', () => applyShuffle(['hardware']));
el('shuffle-graphics').addEventListener('click', () => applyShuffle(['gpu']));
el('shuffle-noise').addEventListener('click', () => applyShuffle(['noise']));
el('export').addEventListener('click', () => {
const blob = new Blob([JSON.stringify(draft, null, 2)], { type: 'application/json' });
const url = URL.createObjectURL(blob);
const anchor = document.createElement('a');
anchor.href = url;
anchor.download = name + '.json';
anchor.click();
URL.revokeObjectURL(url);
setStatus('Exported ' + name + '.json');
});
async function boot() {
const response = await fetch(chrome.runtime.getURL('personas.json'));
mirror = await response.json();
if (!mirror.personas) mirror.personas = {};
try {
const table = await (await fetch(chrome.runtime.getURL('geo.json'))).json();
cities = table.cities || null;
} catch (error) {
cities = null;
}
state = await readState();
// Imported personas live in storage, not personas.json; without this merge a
// reopened page resolves the active name to nothing and exports null.
Object.assign(mirror.personas, state.imports || {});
if (!state.active) state.active = mirror.default || Object.keys(mirror.personas)[0] || null;
renderLocks();
renderPins();
pick(state.active);
if (!Object.keys(mirror.personas).length) {
setStatus('personas.json is empty — run: fps gen, then reload this page.');
}
}
boot();
async function loadTunnels() {
const target = el('vpn-list');
if (!target) return;
try {
const response = await fetch('../data/vpn.json');
if (!response.ok) return;
const data = await response.json();
const seen = (data.tunnels || []).filter((entry) => entry.installed);
const parts = seen.map((entry) => entry.label + ': ' + entry.state);
if (!seen.length && !(data.interfaces || []).length) {
target.textContent = 'No VPN client detected on this machine.';
} else {
target.textContent = parts.concat(
(data.interfaces || []).length ? ['interfaces: ' + data.interfaces.join(', ')] : []
).join(' \u00b7 ');
}
} catch (error) {
}
}
loadTunnels();
function profileNames() {
return Object.keys(mirror.personas || {});
}
function resolved(name) {
return mergePersona(mirror.personas[name], (state.overrides || {})[name]);
}
el('import-pick').addEventListener('click', () => el('import-file').click());
el('import-file').addEventListener('change', async () => {
const file = el('import-file').files && el('import-file').files[0];
if (!file) return;
el('import-text').value = await file.text();
el('import-status').textContent = 'Loaded ' + file.name + ' — press Import.';
});
el('import-apply').addEventListener('click', async () => {
const text = el('import-text').value.trim();
if (!text) {
el('import-status').textContent = 'Import failed: paste a profile or choose a file.';
return;
}
const result = await send({ type: 'importProfile', text, name });
if (!result.ok) {
el('import-status').textContent = 'Import failed: ' + result.error;
return;
}
const stored = await readState();
Object.assign(mirror.personas, stored.imports || {});
if (stored.active) state.active = stored.active;
renderDevices();
pick(stored.active || Object.keys(stored.imports || {}).pop());
el('import-status').textContent = 'Imported ' + result.accepted.join(', ') +
(result.rejected.length ? ' — rejected: ' + result.rejected.join('; ') : '');
});
el('stats-run').addEventListener('click', () => {
const names = profileNames();
const overrides = state.overrides || {};
const edited = names.filter((name) => overrides[name]).length;
const locks = (state.locks || []).length;
el('stats-out').textContent = [
'baked personas   ' + Object.keys(mirror.personas).length,
'imported         ' + Object.keys(state.imports || {}).length,
'edited           ' + edited,
'pins             ' + locks,
'active           ' + (state.active || 'none'),
'schema           v' + state.schemaVersion
].join('\n');
});
el('diff-run').addEventListener('click', () => {
const names = profileNames();
if (names.length < 2) {
el('diff-out').textContent = 'Need two personas to compare.';
return;
}
const select = (id, fallback) => {
const node = el(id);
if (!node.options.length) {
names.sort().forEach((name) => node.add(new Option(name, name)));
}
if (!node.value) node.value = names[fallback] || names[0];
return node.value;
};
const left = resolved(select('diff-a', 0));
const right = resolved(select('diff-b', 1));
const keys = [...new Set([...Object.keys(left), ...Object.keys(right)])].sort();
const lines = keys.filter((key) => JSON.stringify(left[key]) !== JSON.stringify(right[key]))
.map((key) => key.padEnd(20) + String(JSON.stringify(left[key])).slice(0, 30) +
'  ->  ' + String(JSON.stringify(right[key])).slice(0, 30));
el('diff-out').textContent = lines.length ? lines.join('\n') : 'no differences';
});
let confirmingDelete = false;
el('delete').addEventListener('click', async () => {
if (!confirmingDelete) {
confirmingDelete = true;
el('delete').textContent = 'Confirm delete';
el('delete-status').textContent = 'Press again to delete ' + name + '.';
return;
}
confirmingDelete = false;
el('delete').textContent = 'Delete this persona';
const result = await send({ type: 'deleteImported', name });
if (!result.ok) {
el('delete-status').textContent = result.error;
return;
}
delete mirror.personas[name];
renderDevices();
const remaining = Object.keys(mirror.personas);
pick(remaining[0] || null);
el('delete-status').textContent = 'Deleted ' + name + '.';
});
