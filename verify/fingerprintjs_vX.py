def detect_platform(ua):
    if "iPhone" in ua: return "ios"
    if "NT 10.0" in ua: return "windows"
    if "Macintosh" in ua: return "mac"
    return "linux"

def detect_browser(ua):
    u = ua.upper()
    if "EDG" in u: return "edge"
    if "SAFARI" in u and "CHROME" not in u: return "safari"
    return "chrome"

def fingerprint(p):
    plat = detect_platform(p.get("ua", ""))
    br = detect_browser(p.get("ua", ""))
    score = 1.0
    if plat != p.get("platform"): score -= 1.0
    if br != p.get("browser"): score -= 1.0
    if p.get("sensors") and br != "safari": score -= 1.0
    return max(0.0, score)
