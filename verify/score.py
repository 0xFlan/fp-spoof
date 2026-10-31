MIN_BITS = 10.0

def score(p, hard=0.75):
    from verify.fingerprintjs_vX import fingerprint
    from random.fingerprint import entropy_field, getplat
    from fix.reconcile import is_valid
    if not is_valid(p):
        return False, {"reason": ["constrained-reject"]}
    fp = fingerprint(p)
    if fp < hard:
        return False, {"reason": ["fpjs"]}
    return True, {"fpjs": fp}
