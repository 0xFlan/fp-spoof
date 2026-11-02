"""Rendered-UI regression tests.

The typography and layout rules that make this read as a settings page rather
than a dashboard are cheap to break and invisible to a unit test, so they are
measured in a real browser: computed sizes, hairline widths, overflow, contrast
and baseline alignment. No pixels are compared - only the geometry and styles
the screenshots were judged on.
"""

from __future__ import annotations

import json
import time
from pathlib import Path

import pytest

from launcher.launch import chrome_path, launch

REPO = Path(__file__).resolve().parents[1]
EXTENSION = REPO / "extension"

pytestmark = pytest.mark.skipif(
    chrome_path() is None or not (EXTENSION / "manifest.json").exists(),
    reason="needs Chrome and the unpacked extension",
)


@pytest.fixture(scope="module")
def browser():
    mirror = json.loads((EXTENSION / "personas.json").read_text())
    persona = mirror["personas"][mirror["default"]]
    session = launch(persona, url="about:blank", headless=True, extension=str(EXTENSION))
    try:
        if not session.extension_id:
            pytest.skip("headless Chrome could not mount the extension: %s" % session.extension_error)
        yield session
    finally:
        session.close()


class Page:
    """One extension page at a fixed viewport and colour scheme."""

    def __init__(self, session, path, width, height, scheme):
        self.session = session
        target = session.cdp.call("Target.createTarget", {"url": "about:blank"})
        self.target_id = target["targetId"]
        self.sid = session.cdp.call(
            "Target.attachToTarget", {"targetId": target["targetId"], "flatten": True}
        )["sessionId"]
        session.cdp.call("Page.enable", {}, session_id=self.sid)
        session.cdp.call("Runtime.enable", {}, session_id=self.sid)
        session.cdp.call(
            "Emulation.setDeviceMetricsOverride",
            {"width": width, "height": height, "deviceScaleFactor": 1, "mobile": False},
            session_id=self.sid,
        )
        session.cdp.call(
            "Emulation.setEmulatedMedia",
            {"features": [{"name": "prefers-color-scheme", "value": scheme}]},
            session_id=self.sid,
        )
        url = "chrome-extension://%s/%s" % (session.extension_id, path)
        session.cdp.call("Page.navigate", {"url": url}, session_id=self.sid)
        time.sleep(2.0)

    def eval(self, expression):
        return self.session.cdp.evaluate(expression, session_id=self.sid, await_promise=True)

    # --- synthetic input, same path the screenshot harness uses -------------

    def scroll_into(self, selector):
        self.eval("(() => { const el = document.querySelector(%s);"
                  " if (el) el.scrollIntoView({block: 'center'}); return 1; })()"
                  % json.dumps(selector))
        time.sleep(0.18)

    def _centre(self, selector):
        box = self.eval("(() => { const el = document.querySelector(%s);"
                        " const r = el.getBoundingClientRect();"
                        " return { x: r.x + r.width / 2, y: r.y + r.height / 2 }; })()"
                        % json.dumps(selector))
        return box["x"], box["y"]

    def move(self, selector):
        self.scroll_into(selector)
        x, y = self._centre(selector)
        self.session.cdp.call("Input.dispatchMouseEvent",
                              {"type": "mouseMoved", "x": x, "y": y,
                               "button": "none", "buttons": 0}, session_id=self.sid)
        time.sleep(0.15)

    def press(self, selector):
        self.move(selector)
        x, y = self._centre(selector)
        self.session.cdp.call("Input.dispatchMouseEvent",
                              {"type": "mousePressed", "x": x, "y": y, "button": "left",
                               "buttons": 1, "clickCount": 1}, session_id=self.sid)
        time.sleep(0.15)

    def release(self, selector):
        x, y = self._centre(selector)
        self.session.cdp.call("Input.dispatchMouseEvent",
                              {"type": "mouseReleased", "x": x, "y": y, "button": "left",
                               "buttons": 0, "clickCount": 1}, session_id=self.sid)
        time.sleep(0.1)

    def park(self):
        self.session.cdp.call("Input.dispatchMouseEvent",
                              {"type": "mouseMoved", "x": 3, "y": 3,
                               "button": "none", "buttons": 0}, session_id=self.sid)
        time.sleep(0.1)

    def tab_to(self, selector, limit=110):
        """Real Tab key events: a DOM .focus() never raises :focus-visible."""
        self.eval("(() => { const a = document.activeElement;"
                  " if (a && a.blur) a.blur();"
                  " document.body.setAttribute('tabindex', '-1');"
                  " document.body.focus(); return 1; })()")
        tab = {"key": "Tab", "code": "Tab",
               "windowsVirtualKeyCode": 9, "nativeVirtualKeyCode": 9}
        for _ in range(limit):
            self.session.cdp.call("Input.dispatchKeyEvent", dict(tab, type="keyDown"),
                                  session_id=self.sid)
            self.session.cdp.call("Input.dispatchKeyEvent", dict(tab, type="keyUp"),
                                  session_id=self.sid)
            time.sleep(0.03)
            if self.eval("!!(document.activeElement && document.activeElement.matches(%s))"
                         % json.dumps(selector)):
                return True
        return False

    def close(self):
        try:
            self.session.cdp.call("Target.closeTarget", {"targetId": self.target_id})
        except Exception:  # the tab may already be gone; never mask a real failure
            pass


@pytest.fixture(scope="module")
def popup(browser):
    page = Page(browser, "src/popup.html", 360, 620, "light")
    try:
        yield page
    finally:
        page.close()


@pytest.fixture(scope="module")
def editor(browser):
    page = Page(browser, "src/options.html", 1280, 1200, "light")
    try:
        yield page
    finally:
        page.close()


def test_popup_fits_and_uses_the_system_stack(popup):
    look = popup.eval("""({
      font: getComputedStyle(document.body).fontFamily,
      width: Math.round(document.body.getBoundingClientRect().width),
      scrollWidth: document.body.scrollWidth,
      h1: getComputedStyle(document.querySelector('h1')).fontSize
    })""")
    assert look["font"].startswith("-apple-system")
    assert look["width"] == 360
    assert look["scrollWidth"] <= 360, "popup overflows its own width"
    assert look["h1"] == "15px"


def test_no_all_caps_and_no_glyph_affordances(popup):
    upper = popup.eval("""[...document.querySelectorAll('*')]
      .filter(el => getComputedStyle(el).textTransform === 'uppercase')
      .map(el => el.tagName + (el.id ? '#' + el.id : ''))""")
    assert upper == [], "labelled in all caps: %s" % upper

    actions = popup.eval("[...document.querySelectorAll('.actions button, #reroll, #advanced')].map(b => b.textContent.trim())")
    assert actions == ["Reroll", "Apply to this tab", "Advanced \u203a"], actions


def test_pins_look_pressable(popup):
    """A pin with a transparent background reads as a caption, not a control."""
    states = popup.eval("""[...document.querySelectorAll('#locks .chip')].map(chip => ({
      bg: getComputedStyle(chip).backgroundColor,
      on: chip.getAttribute('aria-pressed')
    }))""")
    assert len(states) == 7
    for state in states:
        assert state["bg"] != "rgba(0, 0, 0, 0)", "a pin has no visible surface"
        assert state["on"] in ("true", "false")


def test_editor_bar_aligns_with_the_content_column(editor):
    align = editor.eval("""(() => {
      const bar = document.querySelector('.topbar-inner').getBoundingClientRect();
      const rail = document.querySelector('.rail').getBoundingClientRect();
      const column = document.querySelector('main').getBoundingClientRect();
      return { barLeft: bar.left, railLeft: rail.left, columnRight: column.right,
               barRight: bar.right, columnWidth: column.width };
    })()""")
    assert abs(align["barLeft"] - align["railLeft"]) <= 1, "wordmark is not over the rail"
    assert abs(align["barRight"] - align["columnRight"]) <= 1, "bar does not end with the column"
    assert round(align["columnWidth"]) == 680


def test_editor_type_scale(editor):
    scale = editor.eval("""(() => {
      const h2 = document.querySelector('.card h2');
      const body = getComputedStyle(document.body);
      return {
        h2: [getComputedStyle(h2).fontSize, getComputedStyle(h2).fontWeight,
             getComputedStyle(h2).textTransform],
        body: [body.fontSize, body.fontFamily.split(',')[0].trim()],
        label: getComputedStyle(document.querySelector('.field > label')).fontSize
      };
    })()""")
    assert scale["h2"] == ["17px", "600", "none"]
    assert scale["body"] == ["15px", "-apple-system"]
    assert scale["label"] == "13px"


def test_rows_separate_from_each_other_not_from_headings(editor):
    """No doubled hairlines, and no rule tucked under a section title."""
    rules = editor.eval("""(() => {
      const fields = [...document.querySelectorAll('.field')];
      const widths = fields.map(f => parseFloat(getComputedStyle(f).borderTopWidth));
      const thick = [...document.querySelectorAll('*')]
        .filter(el => parseFloat(getComputedStyle(el).borderTopWidth) > 1)
        .map(el => el.tagName.toLowerCase() + (el.id ? '#' + el.id : '') +
          (typeof el.className === 'string' && el.className
            ? '.' + el.className.trim().split(' ').join('.') : ''));
      const doubled = thick.length;
      const firstInCard = [...document.querySelectorAll('.card')].map(card => {
        const first = card.querySelector('.field');
        if (!first) return null;
        return parseFloat(getComputedStyle(first).borderTopWidth);
      }).filter(v => v !== null);
      return {
        total: fields.length,
        withRule: widths.filter(w => w > 0).length,
        doubled,
        thick,
        firstInCard
      };
    })()""")
    assert rules["total"] >= 12
    assert rules["doubled"] == 0, "a hairline is drawn twice on: %s" % rules["thick"]
    assert all(w == 0 for w in rules["firstInCard"]), "a rule sits directly under a section title"
    assert 0 < rules["withRule"] < rules["total"], "either every row or no row is ruled"


def test_city_picker_sets_zone_and_coordinates_together(editor):
    """Picking a city must move both halves of the location at once."""
    options = editor.eval("document.querySelector('#geo-place').options.length")
    assert options >= 30, "only %s cities offered" % options

    editor.eval("""(() => {
      const place = document.querySelector('#geo-place');
      place.value = 'Asia/Tokyo';
      place.dispatchEvent(new Event('change', { bubbles: true }));
    })()""")
    state = editor.eval("""(() => ({
      zone: document.querySelector('#timezone').value,
      place: document.querySelector('#geo-place').value,
      lat: Number(document.querySelector('#geo-lat').value),
      lon: Number(document.querySelector('#geo-lon').value),
      city: document.querySelector('#geo-city').textContent,
      status: document.querySelector('#geo-status').textContent
    }))()""")
    assert state["zone"] == "Asia/Tokyo", state
    assert state["place"] == "Asia/Tokyo", state
    assert abs(state["lat"] - 35.6895) < 0.01, state
    assert abs(state["lon"] - 139.6917) < 0.01, state
    assert "Tokyo" in state["city"], state
    assert "match" in state["status"].lower(), state


def test_location_warning_appears_beside_the_control(editor):
    """A coordinate the zone contradicts must be flagged where it is set."""
    editor.eval("""(() => {
      const zone = document.querySelector('#timezone');
      zone.value = 'Europe/Berlin';
      zone.dispatchEvent(new Event('change', { bubbles: true }));
      const lat = document.querySelector('#geo-lat');
      lat.value = '35.6895';
      lat.dispatchEvent(new Event('change', { bubbles: true }));
      const lon = document.querySelector('#geo-lon');
      lon.value = '139.6917';
      lon.dispatchEvent(new Event('change', { bubbles: true }));
    })()""")
    status = editor.eval("document.querySelector('#geo-status').textContent")
    count = editor.eval("document.querySelector('#coherence-count').textContent")
    assert "km from" in status, status
    assert "warning" in count.lower(), count


def test_proxy_authoring_names_the_route_and_the_launcher_flag(editor):
    """The per-run override must be discoverable where the proxy is authored."""
    editor.eval("""(() => {
      document.querySelector('#proxy-scheme').value = 'http';
      document.querySelector('#proxy-host').value = '10.0.0.5';
      document.querySelector('#proxy-port').value = '3128';
      document.querySelector('#proxy-apply').click();
    })()""")
    data = editor.eval("""(() => ({
      proxy: document.querySelector('#ro-proxy').textContent,
      bypass: document.querySelector('#ro-bypass').textContent,
      launch: document.querySelector('#ro-launch').textContent,
      applied: document.querySelector('#ap-egress').textContent
    }))()""")
    assert "http://10.0.0.5:3128" in data["proxy"], data
    assert "--proxy http://10.0.0.5:3128" in data["launch"], data
    assert "proxy" in data["applied"].lower(), data


def test_provider_url_fills_fields_and_direct_mode_is_offered(editor):
    """Users arrive with one provider URL, or with a VPN already running."""
    editor.eval("""(() => {
      document.querySelector('#proxy-url').value = 'socks5://alice:s3cret@10.0.0.5:1080';
      document.querySelector('#proxy-paste').click();
    })()""")
    data = editor.eval("""(() => ({
      host: document.querySelector('#proxy-host').value,
      scheme: document.querySelector('#proxy-scheme').value,
      user: document.querySelector('#proxy-username').value,
      proxy: document.querySelector('#ro-proxy').textContent,
      launch: document.querySelector('#ro-launch').textContent,
      mode: document.querySelector('#proxy-mode').value
    }))()""")
    assert data["host"] == "10.0.0.5", data
    assert data["scheme"] == "socks5", data
    assert data["user"] == "alice", data
    assert "socks5://10.0.0.5:1080" in data["proxy"], data
    assert "auth" in data["proxy"], data
    assert data["mode"] == "fixed_servers", data
    assert "--proxy socks5://10.0.0.5:1080" in data["launch"], data

    editor.eval("""(() => {
      const select = document.querySelector('#proxy-mode');
      select.value = 'direct';
      select.dispatchEvent(new Event('change'));
    })()""")
    after = editor.eval("""(() => ({
      proxy: document.querySelector('#ro-proxy').textContent,
      ip: document.querySelector('#ro-ip').textContent
    }))()""")
    assert "direct" in after["proxy"], after
    assert "direct" in after["ip"], after


def test_applied_card_reports_the_resolved_identity(editor):
    data = editor.eval("""(() => ({
      name: document.querySelector('#ap-name').textContent,
      seeds: document.querySelector('#ap-seeds').textContent,
      overrides: document.querySelector('#ap-overrides').textContent
    }))()""")
    assert data["name"] and data["name"] != "-", data
    assert "/" in data["seeds"], data
    assert "generated" in data["overrides"].lower() or "over" in data["overrides"].lower(), data


def test_label_and_control_share_a_baseline(editor):
    rows = editor.eval("""[...document.querySelectorAll('.field:not(.field-stacked)')].map(field => {
      const label = field.querySelector('label');
      const control = field.querySelector('select, input, .inline, .output');
      if (!label || !control) return { name: '(no control)', offset: 0 };
      const a = label.getBoundingClientRect();
      const b = control.getBoundingClientRect();
      return { name: label.textContent.trim().slice(0, 32),
               offset: Math.abs((a.top + a.height / 2) - (b.top + b.height / 2)) };
    })""")
    assert rows, "no fields found"
    worst = max(rows, key=lambda r: r["offset"])
    assert worst["offset"] <= 3, "label/control centres drift %spx in %r" % (
        round(worst["offset"], 1), worst["name"])


def test_stacked_field_puts_its_label_above_the_controls(editor):
    """A field with a chip cluster keeps the label above, never beside."""
    box = editor.eval("""(() => {
      const field = document.querySelector('.field-stacked');
      const label = field.querySelector('label').getBoundingClientRect();
      const control = field.querySelector('.inline').getBoundingClientRect();
      const hint = field.querySelector('.hint').getBoundingClientRect();
      const chips = field.querySelector('.chips').getBoundingClientRect();
      return { labelBottom: label.bottom, controlTop: control.top,
               controlBottom: control.bottom, hintTop: hint.top,
               labelLeft: label.left, hintLeft: hint.left,
               chipsWidth: chips.width };
    })()""")
    assert box["labelBottom"] <= box["controlTop"], "stacked label overlaps its controls"
    assert box["hintTop"] >= box["controlBottom"], "stacked hint wrapped into a side column"
    assert abs(box["hintLeft"] - box["labelLeft"]) <= 1, "stacked hint is not aligned with the label"


def test_controls_in_one_row_are_the_same_height(editor):
    heights = editor.eval("""(() => {
      const rows = [...document.querySelectorAll('.grid-2')].map(grid =>
        [...grid.querySelectorAll('select, input')].map(el => Math.round(el.getBoundingClientRect().height))
      ).filter(list => list.length > 1);
      return rows;
    })()""")
    for row in heights:
        assert len(set(row)) == 1, "mixed control heights in a row: %s" % row


def test_dark_mode_keeps_rules_visible(browser):
    page = Page(browser, "src/options.html", 1280, 1200, "dark")
    try:
        lum = page.eval("""(() => {
          const parse = (c) => (c.match(/\\d+/g) || [0, 0, 0]).slice(0, 3).map(Number);
          const weight = (rgb) => (0.2126 * rgb[0] + 0.7152 * rgb[1] + 0.0722 * rgb[2]) / 255;
          const bg = weight(parse(getComputedStyle(document.body).backgroundColor));
          const rule = weight(parse(getComputedStyle(document.querySelector('.card')).borderTopColor));
          const row = weight(parse(getComputedStyle(document.querySelector('.field + .field')).borderTopColor));
          return { bg, rule, row, bgColor: getComputedStyle(document.body).backgroundColor };
        })()""")
        assert lum["bgColor"] == "rgb(0, 0, 0)", lum["bgColor"]
        assert abs(lum["rule"] - lum["bg"]) >= 0.08, "dark section rule is invisible: %s" % lum
        assert abs(lum["row"] - lum["bg"]) >= 0.05, "dark row hairline is invisible: %s" % lum
    finally:
        page.close()


def test_narrow_viewport_does_not_overflow(browser):
    page = Page(browser, "src/options.html", 900, 1200, "light")
    try:
        wide = page.eval("""(() => {
          const doc = document.documentElement;
          const offenders = [...document.querySelectorAll('*')]
            .filter(el => el.getBoundingClientRect().right > window.innerWidth + 1)
            .map(el => el.tagName + (el.id ? '#' + el.id : ''));
          return { scrollWidth: doc.scrollWidth, innerWidth: window.innerWidth, offenders };
        })()""")
        assert wide["offenders"] == [], "elements overflow at 900px: %s" % wide["offenders"]
        assert wide["scrollWidth"] <= wide["innerWidth"]

        # A stacked rail that spans the page turns its selected row into a
        # full-width band, which reads as a data table rather than a list.
        rail = page.eval("(() => { const r = document.querySelector('.rail');"
                         " const d = document.querySelector('.device');"
                         " return { rail: Math.round(r.getBoundingClientRect().width),"
                         " device: Math.round(d.getBoundingClientRect().width) }; })()")
        assert rail["rail"] <= 380, "rail stretches to %spx when stacked" % rail["rail"]
        assert rail["device"] <= rail["rail"]
    finally:
        page.close()


HOVER_CASES = [
    ("pin chip", ".chip"),
    ("save pill", "#save"),
    ("device tile", ".device"),
    ("number input", "#screenX"),
    ("latitude input", "#geo-lat"),
    ("city select", "#geo-place"),
    ("proxy host", "#proxy-host"),
    ("proxy mode", "#proxy-mode"),
    ("proxy URL", "#proxy-url"),
]


def _bg(page, selector):
    return page.eval("getComputedStyle(document.querySelector(%s)).backgroundColor"
                     % json.dumps(selector))


def test_hover_changes_the_surface_of_every_control(editor):
    """A hover that does not alter the surface is not a state, it is a no-op."""
    failing = []
    for name, selector in HOVER_CASES:
        editor.park()
        resting = _bg(editor, selector)
        editor.move(selector)
        hovered = _bg(editor, selector)
        editor.park()
        if resting == hovered:
            failing.append("%s (%s) did not change: %s" % (name, selector, resting))
    assert failing == [], "no hover feedback: " + "; ".join(failing)


def test_hover_changes_flat_action_colour(editor):
    """The footer action has no fill to tint, so its colour must move instead."""
    selector = "#reset-persona"
    editor.park()
    resting = editor.eval("getComputedStyle(document.querySelector(%s)).color" % json.dumps(selector))
    editor.move(selector)
    hovered = editor.eval("getComputedStyle(document.querySelector(%s)).color" % json.dumps(selector))
    editor.park()
    assert hovered != resting, "footer action (%s) has no hover: stays %s" % (selector, resting)


def test_active_state_is_distinct_from_hover(editor):
    """Press must read as pressed, not as the hover state again."""
    editor.park()
    resting = _bg(editor, "#save")
    editor.move("#save")
    hovered = _bg(editor, "#save")
    editor.press("#save")
    pressed = _bg(editor, "#save")
    editor.release("#save")
    editor.park()
    assert pressed != hovered, "save pill pressed background equals hover (%s)" % pressed
    assert pressed != resting, "save pill pressed background equals resting (%s)" % pressed


def test_focus_visible_ring_is_single_and_uses_the_accent(editor):
    assert editor.tab_to("#screenX"), "could not reach #screenX by keyboard"
    data = editor.eval("""(() => {
      const el = document.activeElement;
      const style = getComputedStyle(el);
      const probe = document.createElement('span');
      probe.style.color = 'var(--accent)';
      document.body.appendChild(probe);
      const accent = getComputedStyle(probe).color;
      probe.remove();
      const ringed = [...document.querySelectorAll('*')].filter(node => {
        const s = getComputedStyle(node);
        return s.outlineStyle !== 'none' && parseFloat(s.outlineWidth) > 0;
      }).map(node => node.tagName + (node.id ? '#' + node.id : ''));
      return {
        matches: el.matches(':focus-visible'),
        name: el.tagName + (el.id ? '#' + el.id : ''),
        style: style.outlineStyle,
        width: parseFloat(style.outlineWidth),
        colour: style.outlineColor,
        offset: parseFloat(style.outlineOffset),
        accent, ringed
      };
    })()""")
    assert data["matches"] is True, "%s focused but not :focus-visible" % data["name"]
    assert data["style"] != "none" and data["width"] > 0, "%s has no focus ring" % data["name"]
    assert data["colour"] == data["accent"], "%s ring is %s, accent is %s" % (
        data["name"], data["colour"], data["accent"])
    assert data["offset"] >= 2, "%s ring sits on the control edge (%spx)" % (data["name"], data["offset"])
    assert data["ringed"] == [data["name"]], "expected exactly one ring, got %s" % data["ringed"]


def test_focus_ring_is_not_clipped_by_an_ancestor(editor):
    assert editor.tab_to(".device"), "could not reach the device tile by keyboard"
    data = editor.eval("""(() => {
      const el = document.activeElement;
      const r = el.getBoundingClientRect();
      const pad = 9;  // 2px ring + 3px offset + slack
      const clipped = [];
      let node = el.parentElement;
      while (node && node !== document.body) {
        const cs = getComputedStyle(node);
        const over = cs.overflow + ' ' + cs.overflowX + ' ' + cs.overflowY;
        if (/hidden|clip|auto|scroll/.test(over)) {
          const b = node.getBoundingClientRect();
          if (b.left > r.left - pad || b.top > r.top - pad ||
              b.right < r.right + pad || b.bottom < r.bottom + pad) {
            clipped.push(node.tagName + '.' + String(node.className).trim());
          }
        }
        node = node.parentElement;
      }
      return { control: el.tagName + '.' + String(el.className).trim(), clipped };
    })()""")
    assert data["clipped"] == [], "%s ring is clipped by %s" % (data["control"], data["clipped"])


def test_profiles_card_controls_work(editor):
    """Import, stats, diff and delete must exist and actually render something."""
    ids = ["import-file", "import-text", "import-apply", "stats-run", "stats-out",
           "diff-a", "diff-b", "diff-run", "diff-out", "delete", "delete-status",
           "verify-run", "verify-note"]
    present = editor.eval("(() => %s.map((id) => !!document.getElementById(id)))()"
                          % str(ids).replace("'", '"'))
    assert all(present), list(zip(ids, present))

    editor.eval("document.querySelector('#stats-run').click()")
    stats = editor.eval("document.querySelector('#stats-out').textContent")
    assert "baked personas" in stats, stats
    assert "schema" in stats, stats

    editor.eval("document.querySelector('#diff-run').click()")
    diff = editor.eval("document.querySelector('#diff-out').textContent")
    assert diff, "diff produced no output"

    disabled = editor.eval("document.querySelector('#verify-run').disabled")
    assert disabled is True
    note = editor.eval("document.querySelector('#verify-note').textContent")
    assert "fps verify" in note, note

    editor.eval("document.querySelector('#import-apply').click()")
    error = editor.eval("document.querySelector('#import-status').textContent")
    assert "Import failed" in error, error


def test_popup_quick_location_and_network_save(popup):
    """The popup answers where and which route, not just who."""
    popup.eval("document.querySelector('#quick').open = true")
    hidden = popup.eval("""(() => {
      const city = document.querySelector('#quick-city');
      city.value = 'Asia/Tokyo';
      const route = document.querySelector('#quick-route');
      route.value = 'fixed_servers';
      route.dispatchEvent(new Event('change', { bubbles: true }));
      document.querySelector('#quick-host').value = '10.0.0.9';
      document.querySelector('#quick-port').value = '3128';
      document.querySelector('#quick-save').click();
      return document.querySelector('#quick-proxy').hidden;
    })()""")
    assert hidden is False, "proxy fields stayed hidden for a proxy route"
    time.sleep(0.8)
    data = popup.eval("""(() => ({
      ip: document.querySelector('#ip-note').textContent,
      note: document.querySelector('#quick-note').textContent,
      summary: document.querySelector('#summary').textContent,
      width: document.body.scrollWidth
    }))()""")
    assert "10.0.0.9:3128" in data["ip"], data
    assert "10.0.0.9:3128" in data["note"], data
    assert "Tokyo" in data["summary"], data
    assert data["width"] <= 360, "open quick panel overflows the popup: %s" % data["width"]

    popup.eval("""(() => {
      const route = document.querySelector('#quick-route');
      route.value = 'direct';
      route.dispatchEvent(new Event('change', { bubbles: true }));
      document.querySelector('#quick-save').click();
    })()""")
    time.sleep(0.6)
    assert "direct" in popup.eval("document.querySelector('#ip-note').textContent").lower()


def test_popup_pin_blocks_an_axis_shuffle(popup):
    """A pinned axis must not move when the shuffle button is pressed."""
    popup.eval("""(() => {
      const chip = [...document.querySelectorAll('#locks .chip')]
        .find((node) => node.textContent === 'Screen');
      chip.click();
    })()""")
    time.sleep(0.6)
    popup.eval("document.querySelector('[data-shuffle=\"screen\"]').click()")
    time.sleep(0.4)
    blocked = popup.eval("document.querySelector('#status').textContent")
    assert "pinned" in blocked.lower(), blocked

    popup.eval("""(() => {
      const chip = [...document.querySelectorAll('#locks .chip')]
        .find((node) => node.textContent === 'Screen');
      chip.click();
    })()""")
    time.sleep(0.6)
    popup.eval("document.querySelector('[data-shuffle=\"screen\"]').click()")
    time.sleep(0.5)
    moved = popup.eval("document.querySelector('#status').textContent")
    assert "Shuffled screen" in moved, moved


def test_editor_section_pin_and_granular_shuffle(editor):
    """Pins live at the section they protect, and shuffles stay unsaved."""
    editor.eval("document.querySelector('[data-lock=\"screen\"]').click()")
    time.sleep(0.6)
    state = editor.eval("""(() => ({
      pin: document.querySelector('[data-lock="screen"]').getAttribute('aria-pressed'),
      chip: [...document.querySelectorAll('#locks .chip')]
        .find((node) => node.textContent === 'Screen').getAttribute('aria-pressed')
    }))()""")
    assert state == {"pin": "true", "chip": "true"}, state

    editor.eval("document.querySelector('[data-lock=\"screen\"]').click()")
    time.sleep(0.4)
    before = editor.eval("document.querySelector('#canvasSeed').value")
    editor.eval("document.querySelector('#shuffle-noise').click()")
    after = editor.eval("document.querySelector('#canvasSeed').value")
    assert after != before, "noise shuffle did not change the canvas seed"
    status = editor.eval("document.querySelector('#randomize-status').textContent")
    assert "Shuffled noise" in status, status
    assert "Not saved" in status, status

    editor.eval("document.querySelector('#save').click()")
    time.sleep(0.8)
    assert "Saved" in editor.eval("document.querySelector('#status').textContent")
