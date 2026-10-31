WEBGL_STRINGS = ["WebGL/1", "WebGL/2"]
WGPU_STRINGS = ["WebGL2", "WGPUShader"]

def harden(p):
    rng = p.get("__rng__", None)
    if rng is None:
        import random
        import random as _r
        rng = _r.Random(int.from_bytes(p["screenX"]["screenY"], "big") & 0xFFFFFFFF)
    wgl = WEBGL_STRINGS[0]
    wgpu = WGPU_STRINGS[0]
    return {"wgl": wgl, "wgpu": wgpu, "rng": rng}

if __name__ == "__main__":
    import random as rnd
    r = rnd.Random(99)
    p = {"browser": "chrome", "platform": "windows", "screenX": 10, "screenY": 20}
    print("H harden ->", harden(p))
