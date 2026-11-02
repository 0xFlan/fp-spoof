(function () {
'use strict';
if (globalThis.__FPS_APPLY__) {
if (globalThis.__FPS_PERSONA__) globalThis.__FPS_APPLY__(globalThis.__FPS_PERSONA__);
return;
}
var realToString = Function.prototype.toString;
var disguised = new WeakMap();
var asNative = typeof globalThis.__fpsAsNative === 'function'
? globalThis.__fpsAsNative
: function (fn) { return fn; };
function hide(fn) {
try { disguised.set(fn, true); } catch (e) { /* non-function */ }
return fn;
}
if (!globalThis.__fpsAsNative) {
var toStringReplacement = function toString() {
if (disguised.has(this)) {
return 'function ' + (this.name || '') + '() { [native code] }';
}
return realToString.call(this);
};
hide(toStringReplacement);
try {
Object.defineProperty(Function.prototype, 'toString', {
value: toStringReplacement, writable: true, configurable: true
});
} catch (e) { /* locked down page */ }
}
function patch(object, name, value) {
if (!object) return;
var getter = hide(function () { return value; });
try {
Object.defineProperty(object, name, {
get: getter, configurable: true, enumerable: true
});
} catch (e) { /* ignore */ }
}
function patchOn(protos, name, value) {
for (var i = 0; i < protos.length; i++) {
var desc = null;
try { desc = Object.getOwnPropertyDescriptor(protos[i], name); } catch (e) { desc = null; }
if (desc) {
var getter = hide(function () { return value; });
try {
Object.defineProperty(protos[i], name, {
get: getter, configurable: true, enumerable: desc.enumerable
});
return true;
} catch (e) { /* try next */ }
}
}
patch(globalThis, name, value);
return false;
}
var ORIGINAL = '__fpsOriginal__';
function wrapMethod(object, name, factory) {
if (!object || typeof object[name] !== 'function') return;
var current = object[name];
var original = current[ORIGINAL] || current;
var replacement = factory(original);
try {
Object.defineProperty(replacement, ORIGINAL, { value: original, configurable: true });
} catch (e) { /* ignore */ }
try {
object[name] = hide(replacement);
} catch (e) { /* ignore */ }
}
function mulberry32(seed) {
var a = seed >>> 0;
return function () {
a = (a + 0x6D2B79F5) | 0;
var t = Math.imul(a ^ (a >>> 15), 1 | a);
t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
};
}
function pluginArray(names) {
var list = [];
for (var i = 0; i < names.length; i++) {
var mime = {
type: 'application/pdf', suffixes: 'pdf',
description: 'Portable Document Format', enabledPlugin: null, length: 1
};
var plugin = {
name: names[i], filename: 'internal-pdf-viewer',
description: 'Portable Document Format', length: 1
};
plugin[0] = mime;
mime.enabledPlugin = plugin;
list.push(plugin);
}
var array = Object.create(PluginArray.prototype);
for (var j = 0; j < list.length; j++) array[j] = list[j];
Object.defineProperty(array, 'length', { get: hide(function () { return list.length; }), configurable: true });
Object.defineProperty(array, 'item', {
value: hide(function item(index) { return list[index] || null; }), configurable: true
});
Object.defineProperty(array, 'namedItem', {
value: hide(function namedItem(name) {
for (var k = 0; k < list.length; k++) if (list[k].name === name) return list[k];
return null;
}),
configurable: true
});
Object.defineProperty(array, Symbol.iterator, {
value: hide(function () { return list[Symbol.iterator](); }), configurable: true
});
return array;
}
function mimeTypeArray(plugins) {
var items = [];
for (var i = 0; i < plugins.length; i++) items.push(plugins[i][0]);
var array = Object.create(MimeTypeArray.prototype);
for (var j = 0; j < items.length; j++) array[j] = items[j];
Object.defineProperty(array, 'length', { get: hide(function () { return items.length; }), configurable: true });
Object.defineProperty(array, 'item', {
value: hide(function item(index) { return items[index] || null; }), configurable: true
});
Object.defineProperty(array, 'namedItem', {
value: hide(function namedItem(name) {
for (var k = 0; k < items.length; k++) if (items[k].type === name) return items[k];
return null;
}),
configurable: true
});
return array;
}
function offsetMinutes(timezone, date) {
try {
var parts = new Intl.DateTimeFormat('en-US', {
timeZone: timezone, hour12: false,
year: 'numeric', month: '2-digit', day: '2-digit',
hour: '2-digit', minute: '2-digit', second: '2-digit'
}).formatToParts(date);
var map = {};
for (var i = 0; i < parts.length; i++) map[parts[i].type] = parts[i].value;
var hour = map.hour === '24' ? 0 : parseInt(map.hour, 10);
var asUTC = Date.UTC(
parseInt(map.year, 10), parseInt(map.month, 10) - 1, parseInt(map.day, 10),
hour, parseInt(map.minute, 10), parseInt(map.second, 10)
);
return Math.round((asUTC - date.getTime()) / 60000);
} catch (e) {
return -date.getTimezoneOffset();
}
}
function apply(persona) {
if (!persona) return;
globalThis.__FPS_APPLIED__ = persona.seed;
var canvasSeed = (persona.canvasSeed | 0) || (((persona.seed | 0) ^ 0x5BF03635) >>> 0) || 1;
var audioSeed = (persona.audioSeed | 0) || ((((persona.seed | 0) >>> 3) ^ 0x9E3779B9) >>> 0) || 2;
var canvasRRandom = mulberry32(canvasSeed);
var audioRandom = mulberry32(audioSeed);
var timezone = persona.timezone || 'UTC';
var navProto = [Navigator.prototype, Object.getPrototypeOf(navigator) || Navigator.prototype];
patchOn(navProto, 'userAgent', persona.ua);
patchOn(navProto, 'appVersion', String(persona.ua || '').replace(/^Mozilla\//, ''));
patchOn(navProto, 'platform', persona.platformKey);
patchOn(navProto, 'vendor', persona.vendor);
patchOn(navProto, 'vendorSub', '');
patchOn(navProto, 'productSub', '20030107');
patchOn(navProto, 'hardwareConcurrency', persona.hardwareConcurrency);
patchOn(navProto, 'maxTouchPoints', persona.maxTouchPoints || 0);
patchOn(navProto, 'webdriver', false);
patchOn(navProto, 'languages', Object.freeze((persona.languagesZ || ['en-US']).slice()));
patchOn(navProto, 'language', (persona.languagesZ || ['en-US'])[0]);
patchOn(navProto, 'doNotTrack', null);
if (persona.deviceMemory === null || persona.deviceMemory === undefined) {
try { delete Navigator.prototype.deviceMemory; } catch (e) { /* ignore */ }
try { delete navigator.deviceMemory; } catch (e) { /* ignore */ }
} else {
patchOn(navProto, 'deviceMemory', persona.deviceMemory);
}
var plugins = pluginArray(persona.plugins || []);
patchOn(navProto, 'plugins', plugins);
patchOn(navProto, 'mimeTypes', mimeTypeArray(persona.plugins || []));
patchOn(navProto, 'pdfViewerEnabled', (persona.plugins || []).length > 0);
var uaData = persona.userAgentData || null;
if (uaData) {
var proto = null;
try {
proto = navigator.userAgentData ? Object.getPrototypeOf(navigator.userAgentData) : null;
} catch (e) { proto = null; }
var data = Object.create(proto || Object.prototype);
patch(data, 'brands', Object.freeze((uaData.brands || []).map(function (b) {
return Object.freeze({ brand: b.brand, version: String(b.version) });
})));
patch(data, 'mobile', !!uaData.mobile);
patch(data, 'platform', uaData.platform === 'ios' ? 'iOS'
: uaData.platform === 'mac' ? 'macOS'
: uaData.platform === 'linux' ? 'Linux' : 'Windows');
Object.defineProperty(data, 'getHighEntropyValues', {
value: hide(function getHighEntropyValues() {
return Promise.resolve({
architecture: uaData.architecture || 'x86',
bitness: uaData.bitness || '64',
brands: data.brands,
fullVersionList: (uaData.brands || []).map(function (b) {
return { brand: b.brand, version: persona.version || '' };
}),
mobile: !!uaData.mobile,
model: '',
platform: data.platform,
platformVersion: uaData.platformVersion || '10.0.0',
uaFullVersion: persona.version || '',
wow64: false
});
}),
configurable: true
});
patchOn(navProto, 'userAgentData', data);
}
var screenProto = [Screen.prototype];
patchOn(screenProto, 'width', persona.screenX);
patchOn(screenProto, 'height', persona.screenY);
patchOn(screenProto, 'availWidth', persona.availX || persona.screenX);
patchOn(screenProto, 'availHeight', persona.availY || persona.screenY);
patchOn(screenProto, 'colorDepth', persona.colorDepth || 24);
patchOn(screenProto, 'pixelDepth', persona.colorDepth || 24);
patchOn([Window.prototype], 'devicePixelRatio', persona.pixelRatio || 1);
patchOn([Window.prototype], 'outerWidth', persona.screenX);
patchOn([Window.prototype], 'outerHeight', persona.screenY);
wrapMethod(Intl.DateTimeFormat.prototype, 'resolvedOptions', function (original) {
return function resolvedOptions() {
var options = original.call(this);
try {
options.timeZone = timezone;
if (persona.languagesZ && persona.languagesZ.length) {
options.locale = persona.languagesZ[0];
}
} catch (e) { /* ignore */ }
return options;
};
});
wrapMethod(Date.prototype, 'getTimezoneOffset', function () {
return function getTimezoneOffset() {
return -offsetMinutes(timezone, new Date(this.getTime()));
};
});
var geo = persona.geo || null;
var watchCounter = 1;
if (geo && globalThis.Geolocation) {
var position = {
coords: {
latitude: Number(geo.latitude),
longitude: Number(geo.longitude),
accuracy: Number(geo.accuracy) || 50,
altitude: null, altitudeAccuracy: null, heading: null, speed: null
},
timestamp: Date.now()
};
wrapMethod(Geolocation.prototype, 'getCurrentPosition', function () {
return function getCurrentPosition(success) {
if (typeof success === 'function') setTimeout(function () { success(position); }, 0);
};
});
wrapMethod(Geolocation.prototype, 'watchPosition', function () {
return function watchPosition(success) {
var id = watchCounter++;
if (typeof success === 'function') setTimeout(function () { success(position); }, 0);
return id;
};
});
wrapMethod(Geolocation.prototype, 'clearWatch', function () {
return function clearWatch() { /* watch ids are never reused */ };
});
if (globalThis.Permissions && Permissions.prototype.query) {
wrapMethod(Permissions.prototype, 'query', function (original) {
return function query(descriptor) {
if (descriptor && descriptor.name === 'geolocation') {
return Promise.resolve({ state: 'granted', onchange: null });
}
return original.apply(this, arguments);
};
});
}
}
var network = persona.connection || null;
if (network) {
var connection = {
effectiveType: network.effectiveType || '4g',
downlink: network.downlink == null ? 10 : network.downlink,
rtt: network.rtt == null ? 50 : network.rtt,
saveData: !!network.saveData,
type: 'wifi',
onchange: null,
addEventListener: hide(function () {}),
removeEventListener: hide(function () {}),
dispatchEvent: hide(function () { return true; })
};
patchOn(navProto, 'connection', connection);
patchOn(navProto, 'mozConnection', connection);
patchOn(navProto, 'webkitConnection', connection);
}
if (globalThis.ScreenOrientation) {
var landscape = Number(persona.screenX) >= Number(persona.screenY);
patchOn([ScreenOrientation.prototype], 'type', landscape ? 'landscape-primary' : 'portrait-primary');
patchOn([ScreenOrientation.prototype], 'angle', 0);
}
if (globalThis.RTCPeerConnection && persona.webrtcPolicy !== 'off') {
var PRIVATE = /(^|[^0-9])(10\.|127\.|169\.254\.|172\.(1[6-9]|2[0-9]|3[01])\.|192\.168\.|fe80:|fc[0-9a-f]{2}:|fd[0-9a-f]{2}:)/i;
function leaks(candidate) {
if (!candidate) return false;
var text = typeof candidate === 'string' ? candidate : (candidate.candidate || '');
return !text || /\.local\b/i.test(text) || PRIVATE.test(text);
}
function guard(handler) {
return hide(function (event) {
if (event && 'candidate' in event && leaks(event.candidate)) return undefined;
return handler.call(this, event);
});
}
wrapMethod(RTCPeerConnection.prototype, 'addEventListener', function (original) {
return function addEventListener(type, listener, options) {
if (type === 'icecandidate' && typeof listener === 'function') {
return original.call(this, type, guard(listener), options);
}
return original.apply(this, arguments);
};
});
var iceDescriptor = null;
try {
iceDescriptor = Object.getOwnPropertyDescriptor(RTCPeerConnection.prototype, 'onicecandidate');
} catch (e) { iceDescriptor = null; }
if (iceDescriptor && iceDescriptor.set) {
try {
Object.defineProperty(RTCPeerConnection.prototype, 'onicecandidate', {
configurable: true, enumerable: iceDescriptor.enumerable,
get: iceDescriptor.get,
set: function (handler) {
iceDescriptor.set.call(this, typeof handler === 'function' ? guard(handler) : handler);
}
});
} catch (e) { /* ignore */ }
}
}
var webglVendor = persona.webglVendor || '';
var webglRenderer = persona.webglRenderer || '';
[globalThis.WebGLRenderingContext, globalThis.WebGL2RenderingContext].forEach(function (ctor) {
if (!ctor) return;
wrapMethod(ctor.prototype, 'getParameter', function (original) {
return function getParameter(parameter) {
if (parameter === 37445) return webglVendor;
if (parameter === 37446) return webglRenderer;
return original.call(this, parameter);
};
});
});
var realGetImageData = globalThis.CanvasRenderingContext2D
&& CanvasRenderingContext2D.prototype.getImageData;
if (realGetImageData) {
wrapMethod(CanvasRenderingContext2D.prototype, 'getImageData', function (original) {
return function getImageData() {
var image = original.apply(this, arguments);
try {
var data = image.data;
var random = mulberry32((canvasSeed ^ data.length) >>> 0);
for (var i = 0; i < data.length; i += 4) {
if (random() < 0.35) {
data[i] ^= (random() < 0.5 ? 1 : 0);
data[i + 1] ^= (random() < 0.5 ? 1 : 0);
data[i + 2] ^= (random() < 0.5 ? 1 : 0);
}
}
} catch (e) { /* ignore */ }
return image;
};
});
wrapMethod(HTMLCanvasElement.prototype, 'toDataURL', function (original) {
return function toDataURL() {
var context = null;
try { context = this.getContext('2d'); } catch (e) { context = null; }
if (!context) return original.apply(this, arguments);
var saved = null;
var copy = null;
try {
saved = realGetImageData.call(context, 0, 0, 1, 1);
copy = new ImageData(new Uint8ClampedArray(saved.data), 1, 1);
var data = saved.data;
data[0] ^= (canvasSeed & 1);
data[1] ^= ((canvasSeed >> 1) & 1);
data[2] ^= ((canvasSeed >> 2) & 1);
context.putImageData(saved, 0, 0);
return original.apply(this, arguments);
} catch (e) {
return original.apply(this, arguments);
} finally {
if (copy) {
try { context.putImageData(copy, 0, 0); } catch (e) { /* ignore */ }
}
}
};
});
}
function addAudioNoise(buffer, scale) {
if (!buffer) return;
var random = mulberry32(audioSeed);
for (var i = 0; i < buffer.length; i++) {
buffer[i] = buffer[i] + (random() - 0.5) * scale;
}
}
[globalThis.AnalyserNode].forEach(function (ctor) {
if (!ctor) return;
wrapMethod(ctor.prototype, 'getFloatFrequencyData', function (original) {
return function getFloatFrequencyData(array) {
original.apply(this, arguments);
addAudioNoise(array, 1e-7);
};
});
wrapMethod(ctor.prototype, 'getByteFrequencyData', function (original) {
return function getByteFrequencyData(array) {
original.apply(this, arguments);
var random = mulberry32(audioSeed);
for (var i = 0; i < array.length; i++) {
if (random() < 0.3) array[i] = (array[i] + (random() < 0.5 ? 1 : -1) + 256) % 256;
}
};
});
});
}
globalThis.__FPS_APPLY__ = apply;
if (globalThis.__FPS_PERSONA__) {
try {
apply(globalThis.__FPS_PERSONA__);
} catch (e) {
if (typeof console !== 'undefined' && console.warn) console.warn('fp-spoof: apply failed', e);
}
}
})();
