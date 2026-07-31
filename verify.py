#!/usr/bin/env python3
"""Compare ADS-B data with passive radar detections."""
import json, math

RX_LAT = 34.25  # Approximate receiver location (Xi'an)
RX_LON = 108.94

# FM transmitter location (88 MHz - Shaanxi TV tower near city center)
TX_LAT = 34.22
TX_LON = 108.95

# Passive radar detections from today's best run
pr_detections = [
    (33.2, 144),  # km, Hz
    (6.2, -130),
    (7.7, 128),
    (34.1, 19),
    (44.8, 110),
    (15.0, 72),
]

def haversine(lat1, lon1, lat2, lon2):
    R = 6371  # km
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = math.sin(dlat/2)**2 + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(dlon/2)**2
    return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1-a))

d = json.load(open("/run/readsb/aircraft.json"))
ac = d.get("aircraft", [])

print("=" * 70)
print("ADS-B vs FM Passive Radar Verification")
print("=" * 70)
print(f"\nReceiver: [{RX_LAT},{RX_LON}] (Xi'an)")
print(f"FM Transmitter (88 MHz): [{TX_LAT},{TX_LON}]")
print()

print("Active Aircraft (from readsb):")
print("-" * 70)
for a in ac:
    lat = a.get("lat")
    lon = a.get("lon")
    if not lat or not lon:
        continue
    
    dist_rx = haversine(RX_LAT, RX_LON, lat, lon)  # km from receiver
    dist_tx = haversine(TX_LAT, TX_LON, lat, lon)  # km from transmitter
    dist_tx_rx = haversine(TX_LAT, TX_LON, RX_LAT, RX_LON)  # tx to rx
    
    # Bistatic range: (tx->target + target->rx - tx->rx)
    bi_range = dist_tx + dist_rx - dist_tx_rx
    
    fl = a.get("flight", "").strip()
    alt = a.get("alt_baro", "?")
    gs = a.get("gs", "?")
    trk = a.get("track", "?")
    rssi = a.get("rssi", "?")
    
    # Check if any passive radar detection is close
    matched = False
    for pr_dist, pr_dopp in pr_detections:
        if abs(bi_range - pr_dist) < 5:  # within 5 km
            matched = True
            print(f"  ⭐ {fl:8s}  ALT={alt:>5}ft  GS={gs:>3}kt  TRK={trk:>5}°  "
                  f"RX-dist={dist_rx:.0f}km  BI-range={bi_range:.0f}km  "
                  f"(matches PR: {pr_dist:.0f}km/{pr_dopp:+.0f}Hz)  RSSI={rssi}")
    
    if not matched:
        print(f"     {fl:8s}  ALT={alt:>5}ft  GS={gs:>3}kt  TRK={trk:>5}°  "
              f"RX-dist={dist_rx:.0f}km  BI-range={bi_range:.0f}km  RSSI={rssi}")

print()
print("Passive Radar detections WITHOUT ADS-B match:")
for pr_dist, pr_dopp in pr_detections:
    matched = False
    for a in ac:
        lat = a.get("lat")
        lon = a.get("lon")
        if not lat or not lon:
            continue
        dist_tx = haversine(TX_LAT, TX_LON, lat, lon)
        dist_rx = haversine(RX_LAT, RX_LON, lat, lon)
        dist_tx_rx = haversine(TX_LAT, TX_LON, RX_LAT, RX_LON)
        bi_range = dist_tx + dist_rx - dist_tx_rx
        if abs(bi_range - pr_dist) < 5:
            matched = True
    if not matched:
        print(f"  {pr_dist:.0f} km  {pr_dopp:+.0f} Hz  (no ADS-B match)")
