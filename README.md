# fp-spoof

fp-spoof is a toolkit for masking and randomizing browser, device, and network fingerprints (Canvas, WebGL, TLS, User-Agent) to bypass tracking and anti-bot checks.
 It can apply a persona in two ways:

- with a Chrome or Edge extension, while you browse normally;
- with a launcher that starts a clean browser and applies the persona through
  the DevTools Protocol.

The tool runs offline. It makes no network calls, needs no account, and sends no
telemetry.

This README follows the plain-language principles of ISO 24495-1: make the
information relevant, findable, understandable, and usable.

## Contents

1. [What this project does](#1-what-this-project-does)
2. [What you need](#2-what-you-need)
3. [Install](#3-install)
4. [Quick start](#4-quick-start)
5. [Use the extension](#5-use-the-extension)
6. [Use the launcher](#6-use-the-launcher)
7. [Compare the extension and the launcher](#7-compare-the-extension-and-the-launcher)
8. [Check that it works](#8-check-that-it-works)
9. [Commands](#9-commands)
10. [How personas stay consistent](#10-how-personas-stay-consistent)
11. [Location and network](#11-location-and-network)
12. [Limits](#12-limits)
13. [Performance](#13-performance)
14. [GUI coverage audit](#14-gui-coverage-audit)
15. [Project layout](#15-project-layout)
16. [Tests](#16-tests)
17. [Appropriate use](#17-appropriate-use)
18. [License](#18-license)

## 1. What this project does

A browser fingerprint is the set of details a website can read from your
browser. Examples are the user agent string, screen size, timezone, language,
number of CPU cores, and graphics card name. Websites use these details to
recognise a browser.

A persona replaces those details with a consistent set for a different device.
The values must agree with each other. For example:

- a Safari persona does not report `deviceMemory`;
- an iPhone persona does not report the Windows platform string;
- a 4K screen does not come with a 1366-pixel-wide viewport.

fp-spoof changes two layers:

- **JavaScript values** that a page can read, such as `navigator.userAgent`,
  `screen.width`, `Intl.DateTimeFormat`, and WebGL renderer strings;
- **HTTP request headers**, such as `User-Agent`, `Accept-Language`, and
  `sec-ch-ua`.

fp-spoof does **not** change TLS. A TLS ClientHello is created below the
extension boundary. Changing it needs a modified Chromium build. Section 12
explains this limit.

## 2. What you need

- Python 3.9 or later.
- Chrome, Chromium, Brave, or Edge for the live checks. The extension itself
  works in Chrome and Edge.
- Node.js for the JavaScript syntax checks and the schema harness.
- macOS, Linux, or Windows. The verified results in this README come from
  Chrome 156 on macOS.

The project has no runtime Python dependencies. The test suite needs `pytest`.

## 3. Install

```bash
cd fp-spoof
uv venv && source .venv/bin/activate    # or: python3 -m venv .venv
uv pip install -e ".[dev]"              # or: pip install -e ".[dev]"
```

This installs the `fps` command. Run `fps --help` to see every command.

## 4. Quick start

```bash
fps gen --all           # create one persona for each browser/platform pair
fps list                # list the stored personas
fps show chrome-windows-0000
fps validate            # re-check every stored persona
```

`fps gen` writes two files that the extension reads:

- `extension/personas.json`: the persona list;
- `extension/geo.json`: the timezone-to-city table used to check location.

To create more personas:

```bash
fps gen -b chrome -p mac -n 5 --seed 100
fps stats               # entropy and how much personas differ
```

`fps gen --all` creates eight personas: one for each supported
browser/platform pair.

## 5. Use the extension

The extension is the everyday option. It works in your normal browser profile.

### 5.1 Load the extension

1. Run `fps gen --all`.
2. Open `chrome://extensions`.
3. Turn on **Developer mode**.
4. Click **Load unpacked**.
5. Select the `extension/` folder.
6. Click the toolbar icon.
7. Pick a persona.
8. Turn the switch on.

After you run `fps gen` again, click **Reload** on the extension card. The popup
reads the persona list from `personas.json`, not from the network.

The extension injects `src/patch.js` into every page. It also rewrites
`User-Agent` and `sec-ch-ua*` request headers with `declarativeNetRequest`.

`fps gen` also writes `src/persona.js`. A content script runs that file and then
`patch.js` in the page's main world at `document_start`. The values are in place
before the page runs its first script. No storage round trip is needed, so there
is no race.

### 5.2 The popup

The popup answers three questions you ask often:

- **Who am I?** Switch device and reroll within your pinned fields.
- **Where am I?** Open **Location & network** and pick a city. The timezone and
  the coordinates move together.
- **What is my IP?** The IP row names the route Chrome uses: a proxy, direct, or
  the operating system route.

The **Location & network** panel also sets the route:

- **System / VPN** follows the operating system route.
- **Direct** ignores the system proxy.
- **Proxy server** uses the scheme, host, and port you enter. Choose `http`,
  `https`, `socks4`, or `socks5`. If the address stays the same, its bypass list
  and HTTP credentials stay. A new address does not inherit the old credentials.
  Chrome cannot authenticate to a SOCKS proxy, so choosing `socks4` or `socks5`
  drops the username and password. The option says *no auth*.

Below the route controls are four shuffle buttons: **Screen**, **CPU**, **GPU**,
and **Noise**. Each one changes only its own group. A pinned group refuses to
change and shows a message.

### 5.3 The advanced page

Open it with **Advanced →** in the popup, or from the extension options.

The advanced page edits one field at a time:

- timezone and ordered languages;
- city and coordinates;
- screen size and device pixel ratio;
- CPU cores and memory;
- WebGL renderer;
- canvas and audio seeds;
- pins.

A sticky section bar moves between cards. Each card has its own **Pin** button.
The **Randomize** card can shuffle all fields or one group: **Screen**, **CPU**,
**GPU**, or **Noise**. A shuffle copies values from another generated device on
the same operating system. It skips pinned groups. Shuffles are not saved until
you click **Save**.

### 5.4 Pins and rerolls

Pins control what a reroll may change. For example, pin **OS** and
**Language / TZ**. Reroll then creates new devices inside that envelope. It does
not shuffle every field at once.

If the pins leave only the current persona, reroll changes its noise seeds
instead of doing nothing.

The popup buttons and the advanced page section buttons use the same stored pin
list. If you unpin a field in one place, it is unpinned in the other.

### 5.5 What you cannot edit

Three values are read-only. The reason is consistency, not missing work.

| Field | Why it is derived |
| --- | --- |
| `userAgent`, `userAgentData.brands` | A user agent that disagrees with the platform, brands, or headers is easier to detect than an unmodified browser. Switch **device** to change it. |
| `navigator.platform`, `platformKey` | This is a legacy alias, such as `Win32` on 64-bit Windows. Editing it by hand makes it disagree with the user agent. |
| `availWidth`, `availHeight` | These values come from the screen size and the operating system bars. They can never be larger than the screen. |

Every other control offers values that a real device reports:

- memory is 4, 8, 16, or 32 GB (4 or 8 GB on iOS);
- pixel ratio is 1, 1.25, 1.5, 2, or 3;
- the WebGL list contains only renderers that this generator produced for the
  same operating system.

The coherence panel still lists values that are possible but unusual, such as a
Tokyo timezone with `en-US`, or an iOS device at 1× pixel ratio. Errors block
**Save**. Warnings do not, because studying detection is a valid use.

### 5.6 Why there is no IP field

An extension cannot change your public IP address. Only a proxy or a VPN can do
that. The advanced page shows the IP as a read-only fact next to TLS and WebRTC.
A text box that changes nothing would be misleading, so the tool does not offer
one.

### 5.7 What the System / VPN route means

The **System / VPN** route is OS-owned. It belongs to the operating system. The
extension and the launcher cannot start, stop, or check a VPN tunnel. Choosing
**System / VPN** only stops the extension from overriding the route. Whatever
the operating system and any VPN client do then applies.

The popup says *follows your OS route*. It does not claim that it changed a
tunnel.

**Proxy server** and **Direct** are real routes:

- the launcher passes `--proxy-server` for a proxy;
- the launcher passes `--no-proxy-server` for direct;
- the end-to-end test observes Chrome using each route, including SOCKS5 against
  a local SOCKS5 listener.

### 5.8 How edits are stored

The extension stores your edits as a small patch in `chrome.storage.local`. The
patch sits on top of the generated persona. When you run `fps gen` again, your
edits still apply. **Reset this device** removes the patch.

Saving writes storage once. The service worker applies the change. If you close
the popup during a save, the extension does not end up half-applied.

## 6. Use the launcher

```bash
fps launch chrome-windows-0000
```

The launcher does four things:

1. It starts Chrome with a temporary profile.
2. It loads the extension.
3. It applies the persona through the DevTools Protocol:
   - `Emulation.setUserAgentOverride` with `userAgentMetadata`;
   - `Emulation.setTimezoneOverride` and `setLocaleOverride`;
   - `setDeviceMetricsOverride`;
   - `Page.addScriptToEvaluateOnNewDocument`, so the patch runs before the first
     page script.
4. It deletes the temporary profile when Chrome closes.

Examples:

```bash
fps launch --dry-run chrome-mac-0003     # show the command without starting
fps launch --headless --url https://example.com
```

Set `FPSPOOF_CHROME=/path/to/binary` to choose a browser.

## 7. Compare the extension and the launcher

| Capability | Extension only | `fps launch` |
| --- | --- | --- |
| `navigator.*`, `screen.*`, `plugins` | yes | yes |
| WebGL vendor and renderer | yes | yes |
| Stable canvas and audio noise | yes | yes |
| `Intl` timezone and `getTimezoneOffset` | yes | yes |
| `navigator.userAgentData` in JavaScript | yes | yes |
| HTTP `User-Agent` header | yes (DNR) | yes (CDP) |
| HTTP `sec-ch-ua*` headers | yes (DNR) | yes (CDP) |
| `Accept-Language` header | best effort | yes |
| Patch runs before the first page script | yes (`document_start`) | yes |
| TLS, JA3, HTTP/2 fingerprint | no | no |
| WebRTC local IP leak | host candidates filtered | filtered, and UDP is blocked when a proxy is set |
| `navigator.geolocation` | yes (the zone's city) | yes |
| `navigator.connection`, `screen.orientation` | yes | yes |
| Public IP and reverse DNS | no; use a proxy | no; use a proxy |
| Font enumeration | no | no |

No extension or launcher can change TLS. A site that fingerprints the TLS
handshake will still see your real client. Section 12 explains this.

## 8. Check that it works

The launcher is also a test harness. It starts a real browser, applies a
persona, serves a local probe page, and compares what the browser reports with
what the persona says.

```bash
fps verify                                  # headless, launcher only
fps verify --headful                        # real window
fps verify --headful --extension            # real window plus the extension
fps verify --browser safari --platform mac --json
```

Each check reads a live value from the browser. A local HTTP server captures the
`User-Agent` and `sec-ch-ua` headers. Canvas is checked twice, then again after
a reload. A second persona is launched to prove that the noise differs between
identities. Audio is checked the same way. The resolved `Intl` locale is also
compared.

### 8.1 Verified results

Measured on Chrome 156 on macOS on 2026-11-02. The full gate ran from a clean
store with `fps gen --all`, then every command below ran once without a break.
There were no skips.

| Check | Command | Result |
| --- | --- | --- |
| Headless, launcher | `fps verify` | **31/31** |
| Headless, extension mounted | `fps verify --extension` | **30/30** |
| Generator across the matrix | `fps gen --all` / `fps validate` | **8/8 valid** |
| Proxy egress, local listener | `pytest tests/test_egress.py` | **2 passed** |
| SOCKS5 egress, local listener | `pytest tests/test_socks.py` | **2 passed** |
| Tunnel detection and egress | `pytest tests/test_vpn_egress.py` | **8 passed** |
| Chrome / Windows persona | `fps verify --browser chrome --platform windows` | **31/31** |
| Edge / Linux persona | `fps verify --browser edge --platform linux` | **31/31** |
| Extension, chrome-windows-0000 | `fps verify --extension --name chrome-windows-0000` | **30/30** |
| Extension, edge-linux-0000 | `fps verify --extension --name edge-linux-0000` | **30/30** |
| Live export, import, re-export | `python tools/live_roundtrip.py` | **0 field differences** |
| Popup to launcher, all routes | `python tools/gui_roundtrip.py` | **31/31**, HTTP proxy, SOCKS5, and direct routes observed |
| Full suite, clean store | `pytest -q` | **150 passed**, no skips |
| Headful, launcher | `fps verify --headful` | **31/31** |
| Safari / macOS and iOS | `fps verify --browser safari --platform mac` / `ios` | **29/29** each |

Safari personas send no client hints. That is correct for Safari, so those
checks expect no hint headers.

### 8.2 What the browser reported

The popup was driven through its real controls: city, route, and Save. The
launcher then started Chrome with the saved persona. Chrome reported:

```
language(s)             de-DE,de,en
Intl timezone           Asia/Tokyo
Intl resolved locale    de-DE
screen                  1600×900, available 1600×876
pixel ratio             1
cores / memory          8 / 16
WebGL vendor            Google Inc. (Intel)
WebGL renderer          ANGLE (Intel, Mesa Intel(R) UHD Graphics 620 (KBL GT2), OpenGL 4.6)
canvas hash             2958468108
audio hash              199851624
geolocation             35.6895, 139.6917
```

All 31 comparisons passed.

### 8.3 Route checks

The same run proved the routes with local listeners:

- **Proxy server**: the proxy received
  `GET http://gui.fpspoof.test:PORT/` in absolute form, with the persona's
  `User-Agent`. The page came back from the proxy.
- **Direct**: the origin server received the request. The proxy received none.
- **SOCKS5**: Chrome completed a real SOCKS5 CONNECT through a local listener.
  The listener saw the requested host and port. The origin received the
  persona's `User-Agent`, and the page came back through the tunnel.
- **System / VPN**: the launcher added no routing flag. The popup said
  *follows your OS route*. The README states the same limit.

The popup also saved the SOCKS5 choice, switched away to direct, and restored
SOCKS5. The restored route had the chosen scheme, the same host and port, and no
username or password.

### 8.4 The extension run also proves `document_start`

The probe page records `navigator.userAgent` in the first inline script in
`<head>`. In the extension run, that value is already the persona's. A patch
that ran later could not win that race.

### 8.5 Timing to know

`src/persona.js` holds the persona from the last `fps gen` and runs at
`document_start`.

If you choose a different persona in the **popup**, the service worker applies
it when the page commits. Reload once after switching if a page's earliest
inline scripts matter. To make a persona apply before every first script, make
it the stored default with `fps gen`.

### 8.6 What the harness does not prove

The harness checks the values that `launcher/launch.py` measures. It does not
test a third-party fingerprinting service. It does not test TLS or JA3.

## 9. Commands

| Command | What it does |
| --- | --- |
| `fps gen` | Create and store personas. Options: `--all`, `-n`, `-b`, `-p`, `--seed`. |
| `fps roll` | Create one new identity and check it before storing. |
| `fps list` | List stored personas. |
| `fps show NAME` | Show one persona in detail. |
| `fps validate [NAME]` | Re-run consistency and entropy checks. |
| `fps stats` | Show entropy and persona spread. |
| `fps export --out FILE` | Write a JSON bundle for another machine. |
| `fps delete NAME` | Delete a persona. |
| `fps launch [NAME]` | Start a browser with the persona applied. |
| `fps verify` | Run the live browser checks. |
| `fps geo [ZONE]` | Show the city and coordinates for a timezone. |
| `fps geo --lat L --lon N` | Find the nearest catalog city. |
| `fps proxy NAME --url URL` | Attach a proxy, for example `http://user:pass@host:8080` or `socks5://host:1080`. |
| `fps proxy NAME --system` | Follow the operating system route. |
| `fps proxy NAME --direct` | Ignore the system proxy. |
| `fps proxy NAME --host H --port P` | Set the proxy field by field. |
| `fps proxy NAME --clear` | Remove the proxy. |
| `fps vpn` | Show what local VPN clients and tunnel interfaces report. |
| `fps vpn --sync` | Write that view to `extension/data/vpn.json`. |
| `fps egress NAME` | Compare the observed public IP and city with the persona. |
| `fps verify --extension --name NAME` | Load the extension and check that persona. |
| `fps diff A B` | Compare two personas field by field. |
| `fps extension` | Print the extension path. Add `--sync` to refresh personas. |

Most commands accept `--json` when a machine-readable result makes sense.

## 10. How personas stay consistent

**Noise is stable, not random.** Reading the same canvas twice must return the
same bytes. A real GPU is deterministic. Random noise on every call is itself a
signal. Canvas and audio noise come from seeds in the persona. They stay the
same across reads, reloads, and browser restarts.

**Patched getters look native.** They convert to
`function () { [native code] }`. A getter that shows JavaScript source is a
common anti-detect tell.

**One rule table drives generation and validation.** The rules come from
`data/browsers.json`. Generation and validation cannot disagree about what
"valid" means.

## 11. Location and network

### 11.1 City, timezone, and coordinates

A persona also has a place. `navigator.geolocation` returns the coordinates of
the persona's timezone city. A permission query for geolocation reports
`granted`, because Chrome does not return a position without permission.

The timezone is the authority:

```bash
fps geo Europe/Berlin                 # Berlin, 52.5200, 13.4050
fps geo --lat 48.86 --lon 2.35        # Europe/Paris
```

Coordinates more than 250 km from the persona's timezone city produce a
warning. You see the warning in `fps validate`, in the editor's coherence list,
and in the test suite. A Tokyo latitude with a Berlin timezone is a
contradiction that a server can read. You can still edit either value. The
warning tells you that the device is now unusual.

### 11.2 Proxy routes

The tool cannot invent an IP address. It can send traffic through a proxy you
control.

```bash
# An HTTP proxy can take credentials.
fps proxy chrome-windows-0000 --url 'http://user:pass@proxy.example:8080'

# A SOCKS5 proxy uses no credentials; Chrome cannot send them.
fps proxy chrome-windows-0000 --url 'socks5://proxy.example:1080'

# Or set the fields one by one.
fps proxy chrome-windows-0000 --scheme http --host 127.0.0.1 --port 8080

# Other routes.
fps proxy chrome-windows-0000 --system   # follow the OS, so an OS VPN applies
fps proxy chrome-windows-0000 --direct   # ignore the system proxy
fps proxy chrome-windows-0000 --clear    # remove our proxy
```

The editor offers the same three routes and a **Provider URL** field. Paste
`scheme://user:pass@host:1080`, and it fills the fields. The popup's short form
also has a scheme selector: `http`, `https`, `socks4`, or `socks5`.

In the extension, a proxy uses `chrome.proxy.settings` in `fixed_servers` mode.
It also sets `webRTCIPHandlingPolicy` to `disable_non_proxied_udp`, so UDP
cannot carry the real address around the proxy. For HTTP and HTTPS proxies,
credentials are answered only for proxy challenges (`isProxy`). A site's own
`401` response never receives them. Chrome's proxy stack cannot authenticate to
SOCKS, so the SOCKS options carry no credentials.

The launcher applies the same route and accepts the same URL forms:

```bash
fps launch chrome-windows-0000                         # persona's proxy
fps launch --proxy 'socks5://proxy.example:1080'       # one-off override
```

Proxy passwords are stored in the extension profile in plain text. Use a
dedicated proxy account. The proxy provider can see the traffic it carries.

### 11.3 VPNs

This project does not configure a VPN. It cannot start, stop, or verify a
tunnel. A settings page that claimed otherwise would be misleading.

Choosing **System / VPN** is the honest control. It removes this project's
proxy, and Chrome uses whatever route the operating system uses, including a
VPN.

`fps vpn` reports what local clients say about themselves:

- Mullvad and Tailscale through their JSON output;
- NordVPN and Proton through their status line;
- WireGuard through the interfaces it lists;
- the tunnel interfaces the operating system exposes.

Tailscale is reported as `mesh` when it runs without an exit node. A mesh
network that is up is not a tunnel that carries your traffic.

```bash
fps vpn                 # who is installed, and what each client reports
fps vpn --sync          # publish that view to the editor
fps egress chrome-windows-0000   # observed IP compared with the persona
```

`fps egress` asks ipinfo.io for your public IP once, when you run it. It
compares the returned city with the persona's coordinates, prints the distance,
and says clearly when a persona without a proxy is showing your real connection.
The request goes to a third party. That is why it is opt-in. `--endpoint`
accepts another compatible JSON service, including one you host.

### 11.4 WebRTC and connection values

`navigator.connection` (`effectiveType`, `downlink`, `rtt`, `saveData`) and
`screen.orientation` follow the persona. ICE host candidates are removed from
`RTCPeerConnection`, so the local network address does not leak over WebRTC even
without a proxy.

## 12. Limits

- **TLS, JA3, HTTP/2 settings, and TCP fingerprints do not change.** Changing
  JA3 needs a modified Chromium build that reorders the TLS ClientHello. An
  extension and the DevTools Protocol cannot do it.
- **WebRTC can still reveal a public address through STUN.** The patch filters
  host candidates. A proxy also blocks non-proxied UDP. A peer can still learn
  your public address through STUN; that is what STUN does.
- **A public IP, reverse DNS, and ISP metadata cannot come from the browser.**
  A proxy is the only control, and it is opt-in.
- **What the egress tests prove:** `tests/test_egress.py` starts a local HTTP
  proxy. It launches Chrome with the extension and a persona that points at the
  proxy. It observes the request arrive at the proxy, including a request for a
  host that cannot resolve. It reads the applied `fixed_servers` setting and the
  WebRTC policy from the extension's service worker. It also proves the
  negative case: a persona with no proxy never contacts the listener and leaves
  the policy at `default`.
- **What the SOCKS5 tests prove:** `tests/test_socks.py` starts a local,
  dependency-free SOCKS5 listener. It drives both the launcher flag and the
  extension's `chrome.proxy` path. The listener records the CONNECT target, the
  origin receives the persona's `User-Agent`, and the page comes back through
  the tunnel. No third-party proxy and no credentials are involved.
- **What the egress tests do not cover:** a real third-party proxy, a
  third-party SOCKS proxy, UDP payloads, a headful run of those tests, and
  anything below HTTP.
- **Chrome cannot authenticate to a SOCKS proxy.** It can route through SOCKS4
  and SOCKS5, but the proxy API has no SOCKS credential field. Use an
  IP-allowlisted SOCKS proxy, or use an authenticated HTTP or HTTPS proxy. The
  popup drops SOCKS credentials instead of pretending to send them.
- **A VPN is not configured or verified.** `system` mode only stops this project
  from overriding the operating system route. Whether a tunnel is up is between
  you and the operating system. The IP row never claims otherwise.
- **`fps vpn` sees only clients with a command-line tool on `PATH`.** A
  GUI-only client can be connected while nothing is reported. It also does not
  prove that a tunnel carries traffic. `fps egress` observes that, and its
  lookup goes to a third party that can log it.
- **Font enumeration, `BatteryManager`, and `getBattery()` are not changed.**
- **`Date.prototype.toString()` uses the host timezone.** Only
  `Intl.DateTimeFormat` and `getTimezoneOffset` follow the persona.
- **Branded Chrome 137 and later ignore `--load-extension`.** `fps launch`
  works around this by mounting the unpacked extension over CDP with
  `Extensions.loadUnpacked`. If that API is unavailable, the browser still
  starts with the persona applied, but without the extension.
- **Mobile personas on a desktop browser are consistent as data, not as
  behaviour.** The browser still behaves like a desktop browser for hover,
  media queries, and input.

## 13. Performance

The original store opened a connection and recreated the schema for every row.
The current store keeps one WAL connection and upserts by name.

Measured with `python tools/bench_store.py` on this machine. The test writes 300
rows to a throwaway database:

```
rows                     300
rows after a second run  300 (names deduped, not duplicated)
journal_mode             wal
```

The command also prints elapsed milliseconds, rows per second, and the speedup.
Those values move with machine load, so this block keeps only the stable facts.
Run `python tools/bench_store.py` to measure the current machine.

Package size, measured with `python tools/bench_package.py`:

```
extension                131.7 KB raw   39.0 KB gzip   18 files
repository total         450.3 KB raw   144.5 KB gzip  74 files
persona mirror           10.6 KB (2% of the total), 8 personas
```

The mirror holds the eight personas written by `fps gen --all`. It grows when
you store more personas. `tools/slim_extension.py` removes indentation and blank
lines from the shipped scripts. It does not remove any control; the capability
audit still reports zero missing IDs.

The project bundles no dependencies. The launcher speaks CDP over a pipe, and
the extension uses plain ES modules.

## 14. GUI coverage audit

`python tools/capability_audit.py` checks that the GUI exposes the product. It
maps each persona field and each command to a control. It exits with an error if
a control ID disappears.

Current output:

- **28 persona and workflow areas** mapped;
- **0 missing control IDs**;
- **65 wired controls** in the advanced page.

The Profiles card covers the remaining tasks:

- **Import JSON** accepts a file or pasted text. It validates with the same
  `check()` the service worker uses, then writes to `chrome.storage.local`.
- **Store stats** shows counts.
- **Diff personas** compares two personas field by field.
- **Delete this persona** removes an imported persona after a second click. A
  baked persona lives in `personas.json`, so the control says so and points to
  `fps delete NAME`.
- **Verify in browser** is disabled on purpose. A page cannot start Chrome. The
  control shows the exact command instead.

Import, stats, diff, and delete run inside the page.

## 15. Project layout

```
api/          generate and probe entry points, plus the fps CLI
data/         browsers.json, the source of truth for personas
data/geo.json timezone to city coordinates
fix/          consistency checks and deterministic seeds
fpr/          catalog, location loading, generation, entropy
models/       Profile data class and SQLite store
verify/       user-agent parsing and the coherence score
launcher/     CDP-over-pipe client and browser launcher/verifier
extension/    MV3 add-on: manifest, patch.js, service worker, popup
tools/        benchmarks, capability audit, slimming, live round trips
tests/        pytest suite
```

The database is at `$FPSPOOF_HOME/pools/profiles.db`. The default home is
`~/.fp-spoof`. Set `FPSPOOF_DB` to use a different database file.

## 16. Tests

```bash
pytest
```

The suite covers:

- generation for every supported browser and platform pair;
- entropy accounting and validation rules;
- location coherence and proxy validation;
- store idempotency;
- the CLI end to end;
- extension assets, including `node --check` on every script;
- a Node harness for `schema.js`;
- a fake `chrome` harness for the proxy and WebRTC logic;
- a live popup-to-launcher run, including a SOCKS5 route;
- observed HTTP proxy and SOCKS5 egress.

`tests/test_egress.py` and `tests/test_socks.py` observe a browser's network
egress. They watch real Chrome reach local listeners and read the applied policy
back from the service worker.

`tests/test_vpn_egress.py` needs no browser and no network. It feeds each
client's output shape to the parser and replaces the egress fetch with a
fixture.

The egress listeners are per test, not shared. With one shared listener, a
request that Chrome sent after `session.close()` could land in the next test's
measurement window. Each test now gets a fresh port, and the session gets half a
second to close before the assertion reads the listener.

## 17. Appropriate use

This is a privacy tool. It makes one browser profile look like many ordinary
devices. It makes fingerprint-based tracking across sessions harder.

Do not use it to:

- evade fraud controls on accounts you do not own;
- scrape in violation of a site's terms;
- run fake accounts at scale.

Use it on systems you own or have permission to test.

## 18. License

No license has been chosen yet. The repository is public so you can read and
review the code. Do not copy, modify, or redistribute it until the owner adds a
license.
