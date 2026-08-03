from skyfield.api import load

for name, cat in [("NOAA 15", "25338"), ("NOAA 18", "28654"), ("NOAA 19", "33591"), ("METEOR-M2", "40069")]:
    try:
        d = load.tle(f"https://celestrak.org/NORAD/elements/gp.php?CATNR={cat}&FORMAT=tle")
        print(name, "-> keys:", list(d.keys()))
    except Exception as e:
        print(name, "FAIL:", e)
