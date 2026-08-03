from skyfield.api import load

try:
    sats = load.tle("https://celestrak.org/NORAD/elements/gp.php?CATNR=25338&FORMAT=tle")
    print("type:", type(sats))
    print("len:", len(sats))
    for s in sats:
        print("sat:", s)
except Exception as e:
    print("ERR:", repr(e))
