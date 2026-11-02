import { readState, mergePersona, check, summarise, effectiveActive, parseImport } from './schema.js';
import { applyNetwork, installProxyAuth } from './network.js';
let activeProxy = null;
self.__FPS_APPLY_NETWORK__ = async (api, persona) => {
activeProxy = (persona && persona.proxy) || null;
return applyNetwork(api, persona);
};
installProxyAuth(chrome, () => activeProxy);
const RULE_ID = 1;
const ALL_RESOURCE_TYPES = [
'main_frame', 'sub_frame', 'stylesheet', 'script', 'image', 'font',
'object', 'xmlhttprequest', 'ping', 'csp_report', 'media', 'websocket', 'other'
];
const PLATFORM_NAMES = {
windows: 'Windows',
mac: 'macOS',
linux: 'Linux',
ios: 'iOS'
};
let mirrorCache = null;
async function loadMirror(force) {
if (mirrorCache && !force) return mirrorCache;
try {
const response = await fetch(chrome.runtime.getURL('personas.json'));
mirrorCache = await response.json();
} catch (error) {
mirrorCache = { default: null, personas: {} };
}
if (!mirrorCache.personas) mirrorCache.personas = {};
return mirrorCache;
}
function resolvePersona(state, mirror) {
if (!state || state.enabled === false) return null;
const name = state.active;
if (!name) return null;
const base = mirror.personas[name];
if (!base) return null;
return mergePersona(base, (state.overrides || {})[name]);
}
async function context() {
const mirror = await loadMirror(false);
const state = await readState();
const merged = { ...mirror, personas: { ...mirror.personas, ...(state.imports || {}) } };
const active = effectiveActive(state, merged);
if (active && active !== state.active) {
state.active = active;
chrome.storage.local.set({ active }).catch(() => {});
}
return { state, mirror: merged, active, persona: resolvePersona({ ...state, active }, merged) };
}
function quoteBrand(brand, version) {
return '"' + brand + '";v="' + version + '"';
}
function secChUa(persona) {
const brands = (persona.userAgentData && persona.userAgentData.brands) || [];
const parts = brands.map((entry) => quoteBrand(entry.brand, entry.version));
if (!parts.some((part) => part.indexOf('Chromium') === 0)) {
const major = String(persona.version || '0').split('.')[0];
parts.push(quoteBrand('Chromium', major));
}
if (!parts.some((part) => part.indexOf('Not_A Brand') === 0 || part.indexOf('Not.A Brand') === 0)) {
parts.push(quoteBrand('Not_A Brand', '24'));
}
return parts.join(', ');
}
async function applyHeaders(persona) {
if (!persona || !persona.ua) return;
const uad = persona.userAgentData || {};
const languages = persona.languagesZ || ['en-US'];
const full = String(persona.version || '');
const headers = [
{ header: 'user-agent', operation: 'set', value: persona.ua },
{ header: 'accept-language', operation: 'set', value: languages.join(',') },
{ header: 'sec-ch-ua', operation: 'set', value: secChUa(persona) },
{ header: 'sec-ch-ua-mobile', operation: 'set', value: uad.mobile ? '?1' : '?0' },
{ header: 'sec-ch-ua-platform', operation: 'set', value: '"' + (PLATFORM_NAMES[persona.platform] || 'Windows') + '"' }
];
if (uad.platformVersion) {
headers.push({ header: 'sec-ch-ua-platform-version', operation: 'set', value: '"' + uad.platformVersion + '"' });
}
if (uad.architecture) {
headers.push({ header: 'sec-ch-ua-arch', operation: 'set', value: '"' + uad.architecture + '"' });
headers.push({ header: 'sec-ch-ua-bitness', operation: 'set', value: '"' + (uad.bitness || '64') + '"' });
}
if (full) {
const brands = (uad.brands || []).map((entry) => quoteBrand(entry.brand, full));
if (brands.length) {
headers.push({ header: 'sec-ch-ua-full-version-list', operation: 'set', value: brands.join(', ') });
}
}
await chrome.declarativeNetRequest.updateDynamicRules({
removeRuleIds: [RULE_ID],
addRules: [{
id: RULE_ID,
priority: 1,
action: { type: 'modifyHeaders', requestHeaders: headers },
condition: { urlFilter: '*', resourceTypes: ALL_RESOURCE_TYPES }
}]
});
}
async function clearHeaders() {
await chrome.declarativeNetRequest.updateDynamicRules({ removeRuleIds: [RULE_ID] });
}
async function applyToTab(tabId, persona) {
if (!persona) return false;
try {
await chrome.scripting.executeScript({
target: { tabId, allFrames: false },
world: 'MAIN',
files: ['src/patch.js']
});
await chrome.scripting.executeScript({
target: { tabId, allFrames: false },
world: 'MAIN',
func: (payload) => {
window.__FPS_PERSONA__ = payload;
if (typeof window.__FPS_APPLY__ === 'function') window.__FPS_APPLY__(payload);
},
args: [persona]
});
return true;
} catch (error) {
return false;
}
}
async function updateBadge(persona) {
try {
if (!persona) {
await chrome.action.setBadgeText({ text: '' });
return;
}
const verdict = summarise(check(persona));
await chrome.action.setBadgeText({ text: 'on' });
await chrome.action.setBadgeBackgroundColor({
color: verdict.level === 'error' ? '#e5484d' : verdict.level === 'warn' ? '#f5a524' : '#30a46c'
});
} catch (error) { /* badge is cosmetic */ }
}
async function sync() {
const { state, active, persona } = await context();
if (persona) {
await applyHeaders(persona);
} else {
await clearHeaders();
}
await self.__FPS_APPLY_NETWORK__(chrome, persona);
await updateBadge(persona);
return { enabled: state.enabled !== false, active, hasPersona: !!persona };
}
async function loadCities() {
try {
return (await (await fetch(chrome.runtime.getURL('geo.json'))).json()).cities || null;
} catch (error) {
return null;
}
}
async function stateSnapshot() {
const { state, mirror, active, persona } = await context();
return {
enabled: state.enabled !== false,
active,
locks: state.locks || [],
overrides: state.overrides || {},
customised: !!(state.overrides || {})[active],
proxy: (persona && persona.proxy) || null,
webrtc: persona && persona.proxy ? 'disable_non_proxied_udp' : 'default',
personas: Object.keys(mirror.personas),
imported: Object.keys(state.imports || {}),
updated: mirror.updated || null,
verdict: persona ? summarise(check(persona)) : null
};
}
chrome.runtime.onInstalled.addListener(() => { sync().catch(() => {}); });
chrome.runtime.onStartup.addListener(() => { sync().catch(() => {}); });
chrome.storage.onChanged.addListener((changes, area) => {
if (area !== 'local') return;
const relevant = ['enabled', 'active', 'overrides', 'locks', 'schemaVersion'];
if (!relevant.some((key) => key in changes)) return;
sync().catch(() => {});
});
chrome.webNavigation.onCommitted.addListener((details) => {
if (details.frameId !== 0) return;
(async () => {
const { persona } = await context();
if (persona) await applyToTab(details.tabId, persona);
})().catch(() => {});
});
chrome.runtime.onMessage.addListener((message, _sender, sendResponse) => {
(async () => {
switch (message && message.type) {
case 'getState': {
sendResponse(await stateSnapshot());
break;
}
case 'setState': {
const patch = message.patch || {};
await chrome.storage.local.set(patch);
await sync();
sendResponse({ ok: true, state: await stateSnapshot() });
break;
}
case 'syncNow': {
await sync();
sendResponse({ ok: true, state: await stateSnapshot() });
break;
}
case 'refresh': {
await loadMirror(true);
sendResponse(await stateSnapshot());
break;
}
case 'applyNow': {
const { persona } = await context();
const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
let ok = false;
if (tab && tab.id && persona) ok = await applyToTab(tab.id, persona);
sendResponse({ ok, state: await stateSnapshot() });
break;
}
case 'setActive': {
await chrome.storage.local.set({ active: message.name });
await sync();
sendResponse({ ok: true, state: await stateSnapshot() });
break;
}
case 'importProfile': {
const { personas, error } = parseImport(message.text);
if (error) {
sendResponse({ ok: false, error: error });
break;
}
const cities = await loadCities();
const imports = { ...((await readState()).imports || {}) };
const accepted = [];
const rejected = [];
for (const [name, persona] of Object.entries(personas)) {
if (!persona || typeof persona !== 'object') {
rejected.push(name + ': not an object');
continue;
}
const problems = check(persona, cities).filter((p) => p.level === 'error');
if (problems.length) {
rejected.push(name + ': ' + problems.map((p) => p.field + ' ' + p.message).join('; '));
continue;
}
imports[name] = persona;
accepted.push(name);
}
if (!accepted.length) {
sendResponse({ ok: false, error: rejected.join(' | ') || 'no personas found' });
break;
}
await chrome.storage.local.set({ imports, active: accepted[accepted.length - 1] });
await sync();
sendResponse({ ok: true, accepted, rejected, state: await stateSnapshot() });
break;
}
case 'deleteImported': {
const state = await readState();
const imports = { ...(state.imports || {}) };
if (!imports[message.name]) {
sendResponse({ ok: false, error: 'only imported personas can be deleted here; baked ones live in personas.json (fps delete NAME)' });
break;
}
delete imports[message.name];
const remaining = [...Object.keys(imports)];
await chrome.storage.local.set({ imports, active: remaining[0] || null });
await sync();
sendResponse({ ok: true, state: await stateSnapshot() });
break;
}
case 'setEnabled': {
await chrome.storage.local.set({ enabled: !!message.enabled });
await sync();
sendResponse({ ok: true, state: await stateSnapshot() });
break;
}
default:
sendResponse({ ok: false, error: 'unknown message' });
}
})().catch((error) => sendResponse({ ok: false, error: String(error) }));
return true;
});
