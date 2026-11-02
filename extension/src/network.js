export function proxyValue(proxy) {
if (!proxy) return null; // null means "system": clearing restores OS routing
const mode = String(proxy.mode || 'fixed_servers').toLowerCase();
if (mode === 'system') return null;
if (mode === 'direct') return { mode: 'direct' };
if (!proxy.host || !proxy.port) return null;
return {
mode: 'fixed_servers',
rules: {
singleProxy: {
scheme: proxy.scheme || 'http',
host: String(proxy.host),
port: Number(proxy.port)
},
bypassList: Array.isArray(proxy.bypass) && proxy.bypass.length
? proxy.bypass.slice()
: ['localhost', '127.0.0.1']
}
};
}
export const proxyConfig = proxyValue;
export function webrtcPolicy(proxy) {
const value = proxyValue(proxy);
return value && value.mode === 'fixed_servers' ? 'disable_non_proxied_udp' : 'default';
}
export function proxyAuth(proxy) {
if (!proxy || !proxy.username) return null;
return {
username: String(proxy.username),
password: String(proxy.password == null ? '' : proxy.password)
};
}
export function installProxyAuth(api, current) {
const webRequest = api && api.webRequest;
if (!webRequest || !webRequest.onAuthRequired || !webRequest.onAuthRequired.addListener) {
return false;
}
webRequest.onAuthRequired.addListener((details, callback) => {
const credentials = details && details.isProxy ? proxyAuth(current()) : null;
callback(credentials ? { authCredentials: credentials } : {});
}, { urls: ['<all_urls>'] }, ['asyncBlocking']);
return true;
}
export async function applyNetwork(api, persona) {
const proxy = (persona && persona.proxy) || null;
const value = proxyValue(proxy);
const applied = { proxy: null, webrtc: null, cleared: false, errors: [] };
try {
const settings = api && api.proxy && api.proxy.settings;
if (settings) {
if (!value) {
await settings.clear({ scope: 'regular' });
applied.cleared = true;
} else {
await settings.set({ value, scope: 'regular' });
applied.proxy = value;
}
}
} catch (error) {
applied.errors.push(String(error));
}
try {
const policy = api && api.privacy && api.privacy.network &&
api.privacy.network.webRTCIPHandlingPolicy;
if (policy) {
const policyValue = webrtcPolicy(proxy);
await policy.set({ value: policyValue, scope: 'regular' });
applied.webrtc = policyValue;
}
} catch (error) {
applied.errors.push(String(error));
}
return applied;
}
