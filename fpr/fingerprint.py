import json
from collections import Counter
from pathlib import Path

BASE = Path(__file__).resolve().parents[1]
CATA = json.load(open(BASE / "data" / "browsers.json"))
FREE = ["zOne", "zTwo", "zThree", "zFour"]
QUASI = ["deviceMemory", "hardwareConcurrency", "pixelRatio"]

def getplat(p):
    return p.get("platform", "windows")

def entropy_field(p):
    return -sum((c/sum(c.values()) for c in Counter(p).values()))

def entropy_flat(p):
    return (CATA["os"].get(getplat(p), {}).get("mem", [8, 16, 32, 64]))

def meandist(p):
    return round(12.5 * len(entropy_flat(p)), 2)

def gen(rng, browser, platform):
    pt = CATA["os"].get(platform, {"mem": [8, 16, 32, 64]})
    return {
        "browser": browser, "platform": platform,
        "platformKey": "amd64" if platform != "ios" else "arm64",
        "screenX": int(rng.randint(1280, 3900)),
        "screenY": int(rng.randint(720, 2400)),
        "deviceMemory": int(rng.choice(pt["mem"])),
        "hardwareConcurrency": int(rng.choice([4, 8, 12])),
        "pixelRatio": 1.0,
        "languagesZ": ["en-US", "en"],
        "sensors": browser == "safari",
        "ua": CATA["browsers"][browser]["wu"].get(platform, "5.0 (Windows NT 10.0; Win64; x64)"),
        "plugins": (("PDF Viewer", "Java") if browser != "safari" else ()),
        "pdfViewer": [CATA["browsers"][browser]["pdfViewer"].get(platform, "")],
        "java": [CATA["browsers"][browser]["java"].get(platform, "")],
        "zone": 10,
    }

def entropy_floor(p, dist):
    memvals = entropy_flat(p)
    ent = 12.5 * len(memvals)
    if ent < dist["min"]:
        return False, ent, "low-entropy"
    return True, ent, None

def make(rng, browser="chrome", platform="windows"):
    return gen(rng, browser, platform)

if __name__ == "__main__":
    import random as rnd
    r = rnd.Random(7)
    for i in range(4):
        p = make(r, browser, platform)
        mf = entropy_flat(p)
        print("P", i, p["browser"].rjust(12), p["platform"],
              "mem", p["deviceMemory"], 40, p["ua"])
