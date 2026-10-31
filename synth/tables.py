"""Generation distributions.

Authored independently of the curated truth catalogue on purpose: the
verifier treats data/browsers.json as ground truth, so the generator must
never read it. tests/test_core.py::test_generator_never_reads_truth enforces
the separation.

These tables describe what this generator can plausibly emit. They are NOT
the detection reference set and must never be used to score output.

Only desktop Chromium engines are representable. Safari was listed here once,
but the renderer drives Chromium, so a Safari profile could only be faked --
and the fakes were detectable, because WebKit genuinely has no
deviceMemory, sends no client hints and exposes no plugins.
"""

SCREENS = {
    "windows": [
        (1920, 1080),
        (2560, 1440),
        (1366, 768),
        (3840, 2160),
        (1600, 900),
        (3440, 1440),
        (1280, 720),
    ],
    "mac": [
        (2560, 1600),
        (1920, 1080),
        (1512, 982),
        (3456, 2234),
        (2880, 1800),
        (1680, 1050),
    ],
    "linux": [(1920, 1080), (2560, 1440), (1366, 768), (3840, 2160), (1600, 900)],
}

# navigator.deviceMemory is bucketed to a power of two and clamped at 8, so
# 4 and 8 are the only values a desktop ever reports. Anything larger is a
# value no browser emits, which is why it is not offered here.
MEMORY = {
    "windows": [4, 8],
    "mac": [4, 8],
    "linux": [4, 8],
}

# Apple shipped 4-core Intel machines and 8/10/12-core Apple silicon, so all
# four occur in the wild. Windows and Linux reach further.
CORES = {
    "windows": [4, 6, 8, 12, 16],
    "mac": [4, 8, 10, 12],
    "linux": [2, 4, 8, 12, 16],
}

DPR = {
    "windows": [1.0, 1.25, 1.5, 2.0],
    "mac": [1.0, 2.0],
    "linux": [1.0, 1.25],
}

# No desktop platform is a touch device.
TOUCH = {
    "windows": (0,),
    "mac": (0,),
    "linux": (0,),
}

# Only offsets with NO daylight saving are offered, so a profile's UTC offset
# is identical in January and July. A DST zone would make the live probe
# disagree with the profile for half the year. See render/timezones.py.
ZONE_OFFSETS = (-7, -5, -3, 0, 1, 9)

ZONES = {
    "windows": ZONE_OFFSETS,
    "mac": ZONE_OFFSETS,
    "linux": ZONE_OFFSETS,
}

# The exact strings navigator.platform reports. Not CPU names: Chromium says
# Win32 / MacIntel / Linux x86_64. The renderer writes this value into
# navigator.platform and the probe reads it back, so anything else here would
# fail every live run.
PLATFORM_KEY = {
    "windows": "Win32",
    "mac": "MacIntel",
    "linux": "Linux x86_64",
}

ALLOWED = {
    "windows": ("chrome", "edge"),
    "mac": ("chrome", "edge"),
    "linux": ("chrome",),
}

LANGUAGES = (
    ("en-US", "en"),
    ("en-GB", "en"),
    ("fr-FR", "fr", "en"),
    ("es-ES", "es", "en"),
    ("ja-JP", "ja", "en"),
    ("pt-BR", "pt", "en"),
)

# A profile draws its language first and its zone from that language's list,
# so an en-US machine can never claim Tokyo. Each pair below is a language
# spoken in a zone that does not observe DST.
LANGUAGE_ZONES = {
    "en-US": (-7,),  # America/Phoenix
    "en-GB": (1,),  # Africa/Lagos
    "fr-FR": (0,),  # Africa/Abidjan
    "es-ES": (-5,),  # America/Bogota
    "ja-JP": (9,),  # Asia/Tokyo
    "pt-BR": (-3,),  # America/Sao_Paulo
}

PLATFORM_TOKENS = {
    "windows": "Windows NT",
    "mac": "Macintosh",
    "linux": "Linux",
}

BROWSER_TOKENS = {
    "chrome": "Chrome/",
    "edge": "Edg/",
}

CHROME_MAJOR = (131, 132, 133, 134, 138, 141)

# Chromium ships the same PDF plugin list on every platform, so the set is a
# property of the browser and nothing else. Edge adds its own viewer entry;
# that difference is real and reconcile() checks the set exactly.
PLUGINS_BY_BROWSER = {
    "chrome": (
        "PDF Viewer",
        "Chrome PDF Viewer",
        "Chromium PDF Viewer",
        "WebKit built-in PDF",
    ),
    "edge": (
        "PDF Viewer",
        "Chrome PDF Viewer",
        "Chromium PDF Viewer",
        "Microsoft Edge PDF Viewer",
        "WebKit built-in PDF",
    ),
}

# What each engine can actually expose. Capability lookups replace "chrome
# probably has it": a driver that renders an engine without
# navigator.deviceMemory declares it here, and reconcile() then rejects any
# profile that claims one. Without this table the contradiction was
# invisible, because the init script defined the property unconditionally.
BROWSER_CAPS = {
    "chrome": {"deviceMemory": True, "clientHints": True, "plugins": True},
    "edge": {"deviceMemory": True, "clientHints": True, "plugins": True},
}

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
}
