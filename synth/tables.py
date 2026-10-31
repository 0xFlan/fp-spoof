"""Generation distributions.

Authored independently of the curated truth catalogue on purpose: the
verifier treats data/browsers.json as ground truth, so the generator must
never read it. tests/test_core.py::test_generator_never_reads_truth enforces
the separation.

These tables describe what this generator can plausibly emit. They are NOT
the detection reference set and must never be used to score output.
"""

SCREENS = {
    "windows": [(1920, 1080), (2560, 1440), (1366, 768), (3840, 2160),
                (1600, 900), (3440, 1440), (1280, 720)],
    "mac": [(2560, 1600), (1920, 1080), (1512, 982), (3456, 2234),
            (2880, 1800), (1680, 1050)],
    "linux": [(1920, 1080), (2560, 1440), (1366, 768), (3840, 2160), (1600, 900)],
    "ios": [(390, 844), (393, 852), (430, 932), (428, 926), (375, 812), (412, 915)],
}

MEMORY = {
    "windows": [4, 8, 16, 32],
    "mac": [8, 16, 32, 64],
    "linux": [4, 8, 16, 32],
    "ios": [4, 6, 8],
}

CORES = {
    "windows": [4, 6, 8, 12, 16],
    "mac": [8, 10, 12],
    "linux": [2, 4, 8, 12, 16],
    "ios": [4, 6],
}

DPR = {
    "windows": [1.0, 1.25, 1.5, 2.0],
    "mac": [1.0, 2.0],
    "linux": [1.0, 1.25],
    "ios": [2.0, 3.0],
}

TOUCH = {
    "windows": [0, 10],
    "mac": [0],
    "linux": [0],
    "ios": [5],
}

ZONES = {
    "windows": [9, 10, 11],
    "mac": [9, 10],
    "linux": [9, 10],
    "ios": [10, 11],
}

PLATFORM_KEY = {
    "windows": "amd64",
    "mac": "x86_64",
    "linux": "x86_64",
    "ios": "arm64",
}

ALLOWED = {
    "windows": ("chrome", "edge"),
    "mac": ("chrome", "safari", "edge"),
    "linux": ("chrome",),
    "ios": ("safari",),
}

LANGUAGES = (
    ("en-US", "en"),
    ("en-GB", "en"),
    ("de-DE", "de", "en"),
    ("fr-FR", "fr", "en"),
    ("es-ES", "es", "en"),
    ("ja-JP", "ja", "en"),
    ("pt-BR", "pt", "en"),
)

PLATFORM_TOKENS = {
    "windows": "Windows NT",
    "mac": "Macintosh",
    "linux": "Linux",
    "ios": "iPhone",
}

BROWSER_TOKENS = {
    "chrome": "Chrome/",
    "edge": "Edg/",
    "safari": "Safari/",
}

CHROME_MAJOR = (131, 132, 133, 134, 138, 141)
SAFARI_VERSION = ("17.4", "17.5", "18.0", "18.1")

PLUGINS_DESKTOP = (
    "PDF Viewer",
    "Chrome PDF Viewer",
    "Chromium PDF Viewer",
    "Microsoft Edge PDF Viewer",
    "WebKit built-in PDF",
)

UA_TEMPLATES = {
    ("chrome", "windows"): (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/{chrome} Safari/537.36"
    ),
    ("chrome", "mac"): (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/{chrome} Safari/537.36"
    ),
    ("chrome", "linux"): (
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/{chrome} Safari/537.36"
    ),
    ("edge", "windows"): (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/{chrome} Safari/537.36 Edg/{chrome}"
    ),
    ("edge", "mac"): (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/{chrome} Safari/537.36 Edg/{chrome}"
    ),
    ("safari", "mac"): (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 "
        "(KHTML, like Gecko) Version/{safari} Safari/605.1.15"
    ),
    ("safari", "ios"): (
        "Mozilla/5.0 (iPhone; CPU iPhone OS 17_5 like Mac OS X) "
        "AppleWebKit/605.1.15 (KHTML, like Gecko) Version/{safari} "
        "Mobile/15E148 Safari/604.1"
    ),
}
