"""api: generate(apply: mint+store), probe(score)."""
import random
from fpr.fingerprint import gen, entropy_flat, entropy_field, getplat, entropy_floor
from fix.reconcile import is_valid
from verify.fingerprintjs_vX import fingerprint
from models.store import insert as db_insert, list_profiles

def make_profile(browser="chrome", platform="windows", seed=111):
    rng = random.Random(seed)
    p = gen(rng, browser, platform)
    floored, ent, reason = entropy_floor(p, {"min": 10.0})
    valid = is_valid(p) and (reason is None)
    if valid:
        db_insert(name=f"profile-{browser}-{platform}",
                  pool="default", browser=browser, platform=platform,
                  entropy=round(ent, 3), fpjs=1.0, hits=0)
    return valid, p

def probe_profile(browser="chrome", platform="windows", seed=3003):
    rng = random.Random(seed)
    p = gen(rng, browser, platform)
    return fingerprint(p), len(entropy_flat(p))

if __name__ == "__main__":
    valid, p = make_profile("chrome", "windows", 111)
    print(p["browser"], p["platform"], "mem", p["deviceMemory"], "flatCnt", len(entropy_flat(p)))
    print("sensors:", p["sensors"], "screenX:", p["screenX"], "ua:", p["ua"])
    print("valid:", valid)
    fp, ent = probe_profile()
    print("probe fp", fp, "flat", ent)

    print(list_profiles())
