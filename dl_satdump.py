import subprocess, sys

url = "https://github.com/SatDump/SatDump/releases/download/1.2.2/satdump_1.2.2_arm64.deb"
mirrors = [
    f"https://ghfast.top/{url}",
    f"https://gh-proxy.com/{url}",
    f"https://mirror.ghproxy.com/{url}",
    url,
]

for m in mirrors:
    print(f"trying: {m}")
    r = subprocess.run(["curl", "-sL", "-m", "120", "-o", "/tmp/satdump.deb", m])
    size = 0
    try:
        import os
        size = os.path.getsize("/tmp/satdump.deb")
    except Exception:
        pass
    print(f"  -> exit={r.returncode} size={size}")
    if size > 30_000_000:
        print("OK")
        sys.exit(0)
print("ALL FAILED")
