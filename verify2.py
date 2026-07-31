#!/usr/bin/env python3
"""Compare ADS-B data with passive radar detections - accurate bistatic."""
import json, math

RX_LAT, RX_LON = 34.25, 108.94  # approximate receiver location

# FM 88 MHz transmitter candidates in Xi'an
tx_candidates = [
    ("Shaanxi TV Tower", 34.201, 108.954),
    ("Changan", 34.233, 108.878),
    ("North Xi'an", 34.308, 108.943),
    ("East Xi'an", 34.258, 109.018),
]

def haversine(lat1, lon1, lat2, lon2):
    R = 6371
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = math.sin(dlat/2)**2 + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(dlon/2)**2
    return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1-a))

# PR detections (bistatic range, Doppler)
pr = [(33.2, 144), (6.2, -130), (7.7, 128), (34.1, 19), (44.8, 110), (15.0, 72)]

d = json.load(open("/run/readsb/aircraft.json"))
ac = d.get("aircraft", [])

print("ADS-B vs FM Passive Radar Verification")
print("=" * 70)
print(f"Receiver: {RX_LAT}, {RX_LON}")
print()

for tx_name, tx_lat, tx_lon in tx_candidates:
    tx_rx = haversine(tx_lat, tx_lon, RX_LAT, RX_LON)
    print(f"\nTX: {tx_name} ({tx_lat},{tx_lon}) - tx_rx={tx_rx:.1f}km")
    print("-" * 50)
    
    for a in ac:
        lat = a.get("lat")
        lon = a.get("lon")
        if not lat or not lon:
            continue
        
        fl = a.get("flight", "").strip()
        alt = a.get("alt_baro", "?")
        gs = a.get("gs", "?")
        trk = a.get("track", "?")
        
        rx_dist = haversine(RX_LAT, RX_LON, lat, lon)
        tx_dist = haversine(tx_lat, tx_lon, lat, lon)
        bi_range = tx_dist + rx_dist - tx_rx
        
        # Check against PR detections
        for pr_dist, pr_dop in pr:
            if abs(bi_range - pr_dist) < 5:
                print(f"  MATCH: {fl:8s} alt={alt}ft gs={gs}kt "
                      f"rx={rx_dist:.0f}km bi={bi_range:.0f}km "
                      f"PR={pr_dist:.0f}km/{pr_dop:+.0f}Hz")
    
print("\nDone. (If no MATCH, try different TX location)")
