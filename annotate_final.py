"""Annotate final PR result with fresh ADS-B."""
from PIL import Image, ImageDraw, ImageFont
import json, math, os

import subprocess
r = subprocess.run(["ssh", "iveco@172.20.10.8", "cat /run/readsb/aircraft.json"],
                   capture_output=True, text=True, timeout=10)
ac_data = json.loads(r.stdout).get("aircraft", [])

RX_LAT, RX_LON = 34.25, 108.94

def haversine(lat1, lon1, lat2, lon2):
    R = 6371
    dlat = math.radians(lat2-lat1)
    dlon = math.radians(lon2-lon1)
    a = math.sin(dlat/2)**2 + math.cos(math.radians(lat1))*math.cos(math.radians(lat2))*math.sin(dlon/2)**2
    return R*2*math.atan2(math.sqrt(a), math.sqrt(1-a))

img = Image.open("pi_final.png")
draw = ImageDraw.Draw(img)

# Use a larger font
font = None
for fp in ["C:\\Windows\\Fonts\\consola.ttf", "C:\\Windows\\Fonts\\segoeui.ttf", "C:\\Windows\\Fonts\\arial.ttf"]:
    if os.path.exists(fp):
        font = ImageFont.truetype(fp, 28)
        break
if not font:
    font = ImageFont.load_default()

for a in ac_data:
    lat = a.get("lat")
    lon = a.get("lon")
    if not lat or not lon: continue
    fl = (a.get("flight") or "-----").strip()
    alt = a.get("alt_baro", "?")
    gs = a.get("gs", 0)
    trk = a.get("track", 0)
    rx_dist = haversine(RX_LAT, RX_LON, lat, lon)
    brg = math.degrees(math.atan2(lon-RX_LON, lat-RX_LAT))
    radial_kt = gs * math.cos(math.radians(trk - (brg+180)))
    doppler_hz = -radial_kt * 0.514 * 91.6 / 300
    x = int(min(max(rx_dist/30*960, 10), 950))
    y = int(min(max((100-doppler_hz)/200*840, 10), 830))
    label = "%s FL%s %.0fkt" % (fl, alt, gs)
    draw.ellipse([x-10,y-10,x+10,y+10], outline="red", width=4)
    draw.text((x+15,y-25), label, fill="red", font=font)

img.save("pi_final_annotated.png")
print("Saved: pi_final_annotated.png")
