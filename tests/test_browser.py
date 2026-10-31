"""Browser tests. Opt in with FP_SPOOF_BROWSER=1 after installing playwright."""
import os

import pytest

pytestmark = pytest.mark.skipif(
    os.environ.get("FP_SPOOF_BROWSER") != "1",
    reason="set FP_SPOOF_BROWSER=1 and install playwright to run",
)


def test_live_page_reports_the_profile():
    from render.driver import session
    from synth.mint import mint
    from verify.browser_probe import PROBE, diff

    profile = mint(111)
    with session(profile, headless=True) as context:
        page = context.new_page()
        page.goto("about:blank")
        observed = page.evaluate(PROBE)

    assert diff(profile, observed) == []


def test_two_profiles_render_differently():
    from render.driver import session
    from synth.mint import mint
    from verify.browser_probe import PROBE

    rendered = []
    for seed in (111, 222):
        with session(mint(seed), headless=True) as context:
            page = context.new_page()
            page.goto("about:blank")
            rendered.append(page.evaluate(PROBE))

    assert rendered[0] != rendered[1]
