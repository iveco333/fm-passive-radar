import sys, subprocess, datetime, os
from skyfield.api import load, Topos

ts = load.timescale()

os.makedirs("/tmp/tle", exist_ok=True)

sats = {}
for name, cat in [("NOAA 15", "25338"), ("NOAA 18", "28654"), ("NOAA 19", "33591"), ("METEOR-M2", "40069")]:
    tle_file = f"/tmp/tle/{name.replace(' ', '_')}.txt"
    url = f"https://celestrak.org/NORAD/elements/gp.php?CATNR={cat}&FORMAT=tle"
    r = subprocess.run(["curl", "-sL", "-m", "20", "-o", tle_file, url])
    try:
        d = load.tle(tle_file)
        key = list(d.keys())
        sats[name] = d[key[-1]] if key else None
        print(f"TLE OK: {name}")
    except Exception as e:
        print(f"TLE FAIL {name}: {e}")

xi = Topos("34.3416 N", "108.9398 E")
t0 = ts.now()
start = t0.utc_datetime()

print(f"\n=== 过境预测 (西安 34.34N 108.94E, 未来 72h, 北京时间) ===")
for name, sat in sats.items():
    if sat is None:
        continue
    passes = []
    for i in range(72 * 60):
        tt = ts.utc(start + datetime.timedelta(minutes=i))
        alt = (sat - xi).at(tt).altaz()[0].degrees
        if alt > 10:
            passes.append((tt, alt))
    windows = []
    if passes:
        cur = [passes[0]]
        for p in passes[1:]:
            if (p[0].utc_datetime() - cur[-1][0].utc_datetime()).total_seconds() <= 180:
                cur.append(p)
            else:
                windows.append(cur)
                cur = [p]
        windows.append(cur)
    for w in windows:
        if len(w) < 3:
            continue
        t_start = w[0][0].utc_datetime() + datetime.timedelta(hours=8)
        peak = max(w, key=lambda x: x[1])
        t_peak = peak[0].utc_datetime() + datetime.timedelta(hours=8)
        dur = (w[-1][0].utc_datetime() - w[0][0].utc_datetime()).total_seconds() / 60
        print(f"{name}: {t_start:%m-%d %H:%M} 起, 峰值 {t_peak:%H:%M} {peak[1]:.0f}°, 持续 {dur:.0f}min")
