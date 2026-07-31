"""Annotate PR result with ADS-B aircraft positions."""
from PIL import Image, ImageDraw
import json, math, urllib.request

# Get fresh ADS-B from Pi
import subprocess, sys
result = subprocess.run(["ssh", "iveco@172.20.10.8", "cat /run/readsb/aircraft.json"],
                       capture_output=True, text=True, timeout=10)
ac_data = json.loads(result.stdout).get("aircraft", [])

RX_LAT, RX_LON = 34.25, 108.94

def haversine(lat1, lon1, lat2, lon2):
    R = 6371
    dlat = math.radians(lat2-lat1)
    dlon = math.radians(lon2-lon1)
    a = math.sin(dlat/2)**2 + math.cos(math.radians(lat1))*math.cos(math.radians(lat2))*math.sin(dlon/2)**2
    return R*2*math.atan2(math.sqrt(a), math.sqrt(1-a))

img = Image.open("pi_new2_result.png")
draw = ImageDraw.Draw(img)

for a in ac_data:
    lat = a.get("lat")
    lon = a.get("lon")
    if not lat or not lon:
        continue
    fl = (a.get("flight") or "-----").strip()
    alt = a.get("alt_baro", "?")
    gs = a.get("gs", 0)
    trk = a.get("track", 0)
    
    rx_dist = haversine(RX_LAT, RX_LON, lat, lon)
    
    # Approximate Doppler
    brg = math.degrees(math.atan2(lon - RX_LON, lat - RX_LAT))
    radial_kt = gs * math.cos(math.radians(trk - (brg + 180)))
    doppler_hz = -radial_kt * 0.514 * 91.6 / 300
    
    x = int(rx_dist / 30 * 960)
    y = int((100 - doppler_hz) / 200 * 840)
    x = max(10, min(950, x))
    y = max(10, min(830, y))
    
    label = "%s FL%s" % (fl, alt)
    draw.ellipse([x-6, y-6, x+6, y+6], outline="lime", width=3)
    draw.text((x+10, y-10), label, fill="lime")

img.save("pi_annotated.png")
print("Saved: pi_annotated.png")
