"""Client hints must tell the same story as the user agent."""

from render.headers import GREASE, headers, major_version
from synth import tables
from synth.mint import mint


def test_chrome_claims_chromium_and_chrome():
    profile = mint(111, "chrome", "windows")
    major = major_version(profile.ua)
    brands = [part.strip() for part in headers(profile)["sec-ch-ua"].split(",")]
    assert brands == [
        GREASE,
        f'"Chromium";v="{major}"',
        f'"Google Chrome";v="{major}"',
    ]


def test_edge_never_claims_to_be_chrome():
    sec_ch_ua = headers(mint(111, "edge", "windows"))["sec-ch-ua"]
    assert "Google Chrome" not in sec_ch_ua
    assert "Microsoft Edge" in sec_ch_ua
    assert "Chromium" in sec_ch_ua


def test_grease_uses_the_spelling_chromium_emits():
    sec_ch_ua = headers(mint(111, "chrome", "windows"))["sec-ch-ua"]
    assert "Not_A Brand" in sec_ch_ua
    assert "Not-A.Brand" not in sec_ch_ua


def test_every_renderable_browser_sends_client_hints():
    for platform, browsers in tables.ALLOWED.items():
        for browser in browsers:
            hints = [
                key
                for key in headers(mint(111, browser, platform))
                if key.startswith("sec-ch-ua")
            ]
            assert hints, (platform, browser)


def test_platform_label_matches_the_minted_platform():
    assert headers(mint(111, "chrome", "mac"))["sec-ch-ua-platform"] == '"macOS"'
    assert headers(mint(111, "chrome", "windows"))["sec-ch-ua-platform"] == '"Windows"'
    assert headers(mint(111, "chrome", "linux"))["sec-ch-ua-platform"] == '"Linux"'


def test_accept_language_matches_navigator_languages():
    profile = mint(111, "chrome", "windows")
    header = headers(profile)["accept-language"]
    assert header.split(",")[0] == profile.languagesZ[0]
    assert len(header.split(",")) == len(profile.languagesZ)
