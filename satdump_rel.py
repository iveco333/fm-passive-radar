import json, urllib.request

req = urllib.request.Request(
    "https://api.github.com/repos/altillimity/satdump/releases/latest",
    headers={"User-Agent": "curl/8"},
)
d = json.load(urllib.request.urlopen(req, timeout=30))
print("tag:", d.get("tag_name"))
for a in d.get("assets", []):
    print(a["name"], "|", a["size"], "bytes |", a["browser_download_url"])
