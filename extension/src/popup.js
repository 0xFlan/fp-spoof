import {
readState,
mergePersona,
derived,
check,
summarise,
rerollCandidates,
nextIdentity,
nextInCycle,
rotateSeeds,
diffPersona,
describeDevice,
describeScreen,
shortUa,
shortGpu,
ipSummary,
normaliseProxy,
quickProxy,
PLATFORM_LABEL,
BROWSER_LABEL,
LOCKABLE
} from './schema.js';
const el = (id) => document.getElementById(id);
const enabledInput = el('enabled');
const personaSelect = el('personas');
const locksBox = el('locks');
const verdict = el('verdict');
const summary = el('summary');
const status = el('status');
const quickNote = el('quick-note');
let mirror = { personas: {}, default: null };
let state = null;
let cities = null;
const send = (message) => new Promise((resolve) => chrome.runtime.sendMessage(message, (r) => resolve(r || {})));
function resolved() {
const name = state && state.active;
if (!name) return null;
return mergePersona(mirror.personas[name], (state.overrides || {})[name]);
}
function labelFor(name) {
const p = mirror.personas[name];
if (!p) return name;
return (PLATFORM_LABEL[p.platform] || p.platform) + ' \u00b7 ' +
(BROWSER_LABEL[p.browser] || p.browser) + (p.version ? ' ' + p.version : '');
}
function renderPersonas() {
const names = Object.keys(mirror.personas);
personaSelect.innerHTML = '';
if (!names.length) {
const option = document.createElement('option');
option.value = '';
option.textContent = 'none \u2014 run: fps gen';
personaSelect.appendChild(option);
personaSelect.disabled = true;
return;
}
personaSelect.disabled = false;
const groups = new Map();
for (const name of names) {
const p = mirror.personas[name] || {};
const group = PLATFORM_LABEL[p.platform] || 'other';
if (!groups.has(group)) groups.set(group, []);
groups.get(group).push(name);
}
for (const [group, members] of groups) {
const optgroup = document.createElement('optgroup');
optgroup.label = group;
for (const name of members) {
const option = document.createElement('option');
option.value = name;
option.textContent = labelFor(name);
optgroup.appendChild(option);
}
personaSelect.appendChild(optgroup);
}
if (state.active) personaSelect.value = state.active;
}
function renderLocks() {
const pinned = new Set(state.locks || []);
locksBox.innerHTML = '';
for (const item of LOCKABLE) {
const chip = document.createElement('button');
chip.type = 'button';
chip.className = 'chip' + (pinned.has(item.key) ? ' on' : '');
chip.textContent = item.label;
chip.setAttribute('aria-pressed', pinned.has(item.key) ? 'true' : 'false');
chip.addEventListener('click', () => toggleLock(item.key));
locksBox.appendChild(chip);
}
}
function renderQuick() {
const persona = resolved();
const cityNode = el('quick-city');
if (!cityNode) return;
cityNode.innerHTML = '';
if (cities) {
cityNode.disabled = false;
const entries = Object.entries(cities)
.filter(([, entry]) => entry && entry.city)
.sort((a, b) => String(a[1].city).localeCompare(String(b[1].city)));
for (const [zone, entry] of entries) {
const option = document.createElement('option');
option.value = zone;
option.textContent = entry.city + (entry.country ? ', ' + entry.country : '') + ' \u2014 ' + zone;
cityNode.appendChild(option);
}
if (persona && cities[persona.timezone]) cityNode.value = persona.timezone;
} else {
const option = document.createElement('option');
option.value = '';
option.textContent = 'location table unavailable \u2014 run: fps gen';
cityNode.appendChild(option);
cityNode.disabled = true;
}
const proxy = persona && persona.proxy;
const mode = proxy ? String(proxy.mode || 'fixed_servers') : 'system';
el('quick-route').value = mode;
el('quick-proxy').hidden = mode !== 'fixed_servers';
el('quick-scheme').value = proxy && proxy.scheme ? proxy.scheme : 'http';
el('quick-host').value = proxy && proxy.host ? proxy.host : '';
el('quick-port').value = proxy && proxy.port ? proxy.port : '';
quickNote.textContent = persona ? ipSummary(persona) : '';
}
function renderSummary() {
const persona = resolved();
if (!persona) {
summary.innerHTML = '<div><span>no persona</span><b>run: fps gen</b></div>';
verdict.className = 'verdict';
verdict.textContent = '';
return;
}
const ipNode = document.getElementById('ip-note');
if (ipNode) ipNode.textContent = ipSummary(persona);
const city = cities && cities[persona.timezone] ? cities[persona.timezone].city : null;
const rows = [
['user agent', shortUa(persona)],
['screen', describeScreen(persona)],
['cores / mem', persona.hardwareConcurrency + ' / ' + (persona.deviceMemory == null ? 'n/a' : persona.deviceMemory + ' GB')],
['locale', ((persona.languagesZ || []).join(',') || '?') + ' \u00b7 ' + (persona.timezone || '?') +
(city ? ' \u00b7 ' + city : '')],
['gpu', shortGpu(persona)],
['device', describeDevice(persona)]
];
summary.innerHTML = rows
.map(([key, value]) => '<div><span>' + key + '</span><b>' + String(value) + '</b></div>')
.join('');
const problems = check(persona);
const verdictInfo = summarise(problems);
verdict.className = 'verdict ' + verdictInfo.level;
verdict.textContent = verdictInfo.text;
const pinned = (state.locks || []).length;
if (problems.length) {
const details = problems.slice(0, 3).map((p) => p.message).join(' \u00b7 ');
verdict.title = details + (pinned && problems[0].level === 'warn' ? ' (pinned fields are not auto-fixed)' : '');
} else {
verdict.title = '';
}
}
async function toggleLock(key) {
const locks = new Set(state.locks || []);
if (locks.has(key)) locks.delete(key);
else locks.add(key);
await persist({ locks: [...locks] });
renderLocks();
renderSummary();
renderQuick();
status.textContent = 'Pinned: ' + (locks.size ? [...locks].join(', ') : 'none');
}
async function persist(patch) {
const result = await send({ type: 'setState', patch });
state = { ...state, ...(result.state || {}) };
return result;
}
async function commit(next, message) {
const name = state.active;
const base = mirror.personas[name];
if (!base) return;
const patch = diffPersona(base, derived(next));
const overrides = { ...(state.overrides || {}) };
if (Object.keys(patch).length) overrides[name] = patch;
else delete overrides[name];
await persist({ overrides });
await send({ type: 'applyNow' });
renderSummary();
renderQuick();
status.textContent = message;
}
async function reroll() {
const name = state.active || mirror.default || Object.keys(mirror.personas)[0];
if (!name) return;
const candidates = rerollCandidates(mirror.personas, name, state.locks);
const next = nextInCycle(candidates, name);
if (next && next !== name) {
await persist({ active: next });
personaSelect.value = next;
await send({ type: 'applyNow' });
renderSummary();
renderQuick();
status.textContent = 'Rerolled to ' + labelFor(next) + '. Reload to apply.';
} else {
const persona = resolved();
const rotated = rotateSeeds(persona);
await commit(rotated, 'Only one persona matches the pins \u2014 reshuffled its noise.');
}
}
async function reshuffle() {
const next = nextIdentity(Object.keys(mirror.personas), state.active);
if (!next || next === state.active) {
status.textContent = 'Only one persona exists \u2014 run: fps gen for more.';
return;
}
await persist({ active: next });
personaSelect.value = next;
await send({ type: 'applyNow' });
renderSummary();
renderQuick();
status.textContent = 'New identity: ' + labelFor(next) + '. Applied to this tab.';
}
const SHUFFLE_FIELDS = {
screen: ['screenX', 'screenY', 'pixelRatio'],
hardware: ['hardwareConcurrency', 'deviceMemory'],
gpu: ['webglRenderer']
};
async function shuffle(group) {
const persona = resolved();
if (!persona) return;
if ((state.locks || []).includes(group)) {
status.textContent = group + ' is pinned \u2014 unpin it to shuffle.';
return;
}
const next = { ...persona };
if (group === 'noise') {
Object.assign(next, rotateSeeds(persona));
} else {
const same = Object.entries(mirror.personas)
.filter(([name, p]) => p && name !== state.active && p.platform === persona.platform);
const pool = same.length ? same : Object.entries(mirror.personas)
.filter(([name, p]) => p && name !== state.active);
if (!pool.length) {
status.textContent = 'Only one persona \u2014 run: fps gen for more.';
return;
}
const source = pool[Math.floor(Math.random() * pool.length)][1];
for (const field of SHUFFLE_FIELDS[group] || []) {
if (source[field] !== undefined) next[field] = source[field];
}
}
await commit(next, 'Shuffled ' + group + '. Reload to apply.');
}
async function saveQuick() {
const persona = resolved();
if (!persona) return;
const next = { ...persona };
const zone = el('quick-city').value;
if (zone && cities && cities[zone]) {
next.timezone = zone;
next.geo = { ...cities[zone] };
}
const mode = el('quick-route').value;
let result;
if (mode === 'fixed_servers') {
result = quickProxy(persona.proxy, el('quick-host').value.trim(), Number(el('quick-port').value), el('quick-scheme').value);
} else {
result = { proxy: { mode }, error: null };
}
if (result.error) {
quickNote.textContent = 'Proxy: ' + result.error;
return;
}
next.proxy = result.proxy;
await commit(next, 'Saved location and network. Reload to apply the JavaScript side; headers are live.');
}
async function init() {
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
if (!state.active) state.active = mirror.default || Object.keys(mirror.personas)[0] || null;
enabledInput.checked = state.enabled !== false;
renderPersonas();
renderLocks();
renderSummary();
renderQuick();
if (!Object.keys(mirror.personas).length) {
status.textContent = 'personas.json is empty \u2014 run: fps gen';
} else if (state.overrides && state.overrides[state.active] &&
Object.keys(state.overrides[state.active]).length) {
status.textContent = 'Customised in Advanced.';
} else {
status.textContent = '';
}
}
enabledInput.addEventListener('change', async () => {
await persist({ enabled: enabledInput.checked });
await send({ type: 'syncNow' });
status.textContent = enabledInput.checked ? 'Spoofing enabled.' : 'Spoofing disabled.';
});
personaSelect.addEventListener('change', async () => {
await persist({ active: personaSelect.value });
await send({ type: 'applyNow' });
renderSummary();
renderQuick();
status.textContent = 'Active: ' + labelFor(personaSelect.value) + '. Reload to apply.';
});
el('reroll').addEventListener('click', reroll);
el('reshuffle').addEventListener('click', reshuffle);
el('quick-route').addEventListener('change', () => {
el('quick-proxy').hidden = el('quick-route').value !== 'fixed_servers';
});
el('quick-save').addEventListener('click', saveQuick);
document.querySelectorAll('[data-shuffle]').forEach((button) => {
button.addEventListener('click', () => shuffle(button.dataset.shuffle));
});
el('network-link').addEventListener('click', () => {
chrome.tabs.create({ url: chrome.runtime.getURL('src/options.html') + '#network' });
});
el('apply').addEventListener('click', async () => {
const result = await send({ type: 'applyNow' });
status.textContent = result.ok
? 'Applied. JavaScript patches need a page reload; headers are already live.'
: 'Could not apply to this tab (restricted page?).';
});
el('advanced').addEventListener('click', () => {
chrome.runtime.openOptionsPage();
});
init();
