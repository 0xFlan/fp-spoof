def reconcile(p):
    errors = []
    b = p.get("browser", "")
    plat = p.get("platform", "")
    key = p.get("platformKey", "")
    if b == "safari":
        if p["sensors"] != True or p["touchPoints"] != 7 or p["plugins"]:
            errors.append("safari-inconsistent")
    if plat in ("windows", "mac"):
        if key != "amd64" and "x86_64" not in str(key):
            errors.append("arch-mismatch")
    if "iPhone" in p["ua"] and plat != "ios":
        errors.append("ua-token")
    if plat == "ios" and "iPhone" not in p["ua"]:
        errors.append("ua-token2")
    return errors

def is_valid(p):
    return not reconcile(p)
