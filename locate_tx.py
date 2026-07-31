#!/usr/bin/env python3
"""Triangulate FM transmitter location from PR + ADS-B matches."""
import json, math

RX_LAT, RX_LON = 34.25, 108.94

def haversine(lat1, lon1, lat2, lon2):
    R = 6371
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = math.sin(dlat/2)**2 + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(dlon/2)**2
    return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1-a))

d = json.load(open("/run/readsb/aircraft.json"))
ac = d.get("aircraft", [])

# Build list of (aircraft_id, lat, lon, bistatic_range, doppler)
# From our verification: CHH7265 at 15km/+72Hz matched bi_range ~13-19km
# And CES6534 at 33km from rx possibly matching 33.2km PR

matches = []
for a in ac:
    lat = a.get("lat")
    lon = a.get("lon")
    if not lat or not lon: continue
    fl = a.get("flight", "").strip()
    rx_dist = haversine(RX_LAT, RX_LON, lat, lon)
    
    # Check which PR detections might match
    if abs(rx_dist - 15) < 5:
        matches.append((fl, lat, lon, 15.0, 72, "CHH7265 match"))
    if abs(rx_dist - 33) < 5:
        matches.append((fl, lat, lon, 33.2, 144, "CES6534 candidate"))
    if abs(rx_dist - 34) < 5:
        matches.append((fl, lat, lon, 34.1, 19, "34km candidate"))
    if abs(rx_dist - 12) < 8:
        # Check if this could be the 6.2 or 7.7 km detections
        matches.append((fl, lat, lon, rx_dist, 0, "close candidate"))

print("=" * 70)
print("FM Transmitter Location Triangulation")
print("=" * 70)
print(f"Receiver: {RX_LAT}, {RX_LON}")
print()
print("Available ADS-B targets for triangulation:")
for fl, lat, lon, bi, dop, note in matches:
    rx_d = haversine(RX_LAT, RX_LON, lat, lon)
    print(f"  {fl:8s}  [{lat:.4f},{lon:.4f}]  rx={rx_d:.0f}km  bi={bi:.0f}km  ({note})")

if len(matches) < 2:
    print("\nNeed at least 2 targets. Trying all aircraft...")
    for a in ac:
        lat = a.get("lat")
        lon = a.get("lon")
        if lat and lon:
            fl = a.get("flight", "").strip()
            rx_d = haversine(RX_LAT, RX_LON, lat, lon)
            print(f"  {fl:8s}  [{lat:.4f},{lon:.4f}]  rx={rx_d:.0f}km")

# Try to find TX location using grid search
# For each pair of detections with known bi_range, solve for tx
print("\nGrid search for TX location...")
print("The equation: d(tx, ac) + d(ac, rx) - d(tx, rx) = bi_range")
print()

# Search area: Xi'an region
best_error = float('inf')
best_tx = None
results = []

for tx_lat_deg in range(3410, 3430):  # 34.10 to 34.30
    for tx_lon_deg in range(10870, 10910):  # 108.70 to 109.10
        tx_lat = tx_lat_deg / 100
        tx_lon = tx_lon_deg / 100
        
        tx_rx = haversine(tx_lat, tx_lon, RX_LAT, RX_LON)
        total_error = 0
        valid_matches = 0
        
        for fl, ac_lat, ac_lon, bi_range, dop, note in matches:
            tx_ac = haversine(tx_lat, tx_lon, ac_lat, ac_lon)
            computed_bi = tx_ac + haversine(RX_LAT, RX_LON, ac_lat, ac_lon) - tx_rx
            error = abs(computed_bi - bi_range)
            total_error += error
            valid_matches += 1
        
        if valid_matches >= 2:
            avg_error = total_error / valid_matches
            if avg_error < best_error:
                best_error = avg_error
                best_tx = (tx_lat, tx_lon, avg_error)
                results.append((tx_lat, tx_lon, avg_error))

# Show top results
results.sort(key=lambda x: x[2])
print("Top 5 TX location candidates:")
for lat, lon, err in results[:5]:
    dist_from_rx = haversine(lat, lon, RX_LAT, RX_LON)
    print(f"  [{lat:.4f}, {lon:.4f}]  error={err:.1f}km  rx_dist={dist_from_rx:.0f}km")

if best_tx:
    tx_lat, tx_lon, err = best_tx
    tx_rx = haversine(tx_lat, tx_lon, RX_LAT, RX_LON)
    print(f"\nBest estimate: TX at [{tx_lat:.4f}, {tx_lon:.4f}]")
    print(f"  Error: {err:.1f}km")
    print(f"  Distance from receiver: {tx_rx:.1f}km")
    print(f"  Direction from receiver: ", end="")
    bearing = math.degrees(math.atan2(tx_lon - RX_LON, tx_lat - RX_LAT))
    print(f"{bearing:.0f} deg from north")
    
    # Check known transmitters
    known = [
        ("Shaanxi TV Tower", 34.201, 108.954),
        ("Changan", 34.233, 108.878),
        ("North Xi'an", 34.308, 108.943),
    ]
    print("\nNearest known transmitters:")
    for name, klat, klon in known:
        d = haversine(tx_lat, tx_lon, klat, klon)
        print(f"  {name}: {d:.1f}km from estimate")
