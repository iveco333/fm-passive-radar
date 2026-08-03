import json, subprocess, sys, urllib.request

pkgs = ["certifi", "jplephem", "sgp4"]

def get_url(pkg):
    req = urllib.request.Request(f"https://pypi.org/pypi/{pkg}/json", headers={"User-Agent": "curl/8"})
    d = json.load(urllib.request.urlopen(req, timeout=30))
    # 优先纯 python wheel
    for u in d["urls"]:
        fn = u["filename"]
        if fn.endswith(".whl") and "py3-none-any" in fn:
            return u["url"], fn
    for u in d["urls"]:
        if fn.endswith(".whl"):
            return u["url"], u["filename"]
    return d["urls"][0]["url"], d["urls"][0]["filename"]

for p in pkgs:
    try:
        url, fn = get_url(p)
        print(f"Downloading {fn} ...")
        subprocess.run(["curl", "-sL", "-m", "90", "-o", f"/tmp/{fn}", url], check=True)
        print(f"OK {fn}")
    except Exception as e:
        print(f"FAIL {p}: {e}")
