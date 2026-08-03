#!/usr/bin/env python3
"""解码 adsb_lo_shift.bin (已 LO 偏移+DC阻挡的 1090 IQ)"""
import sys, os, time
import numpy as np
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import pyModeS as pms

FS = 2.4e6
iq = np.fromfile(os.path.join(os.path.dirname(os.path.abspath(__file__)), "adsb_lo_shift.bin"), dtype=np.complex64)
print(f"loaded {len(iq)} samples ({len(iq)/FS:.2f}s)", flush=True)

mag = np.abs(iq)
p99 = np.percentile(mag, 99)
thr = p99 * 0.8
bit = int(FS * 1e-6)
n = len(mag)
above = mag > thr

def decode_frame(sig, start, n_bits):
    bits = []
    for b in range(n_bits):
        s = start + 8 * bit + b * bit
        if s + bit >= len(sig):
            return None
        win = sig[s:s + bit]
        bits.append(1 if np.mean(win) > thr else 0)
    return "".join(str(b) for b in bits)

found = 0
seen = set()
for i in range(200, n - 300):
    if not above[i]:
        continue
    try:
        if above[i+bit] and above[i+2*bit] and above[i+int(3.5*bit)]:
            if not above[i+bit//2] and not above[i+bit+bit//2]:
                hex_str = decode_frame(mag, i, 112)
                if hex_str:
                    try:
                        m = pms.Message(hex_str)
                        d = m.decode()
                        icao = d.get("icao", "?")
                        if icao not in seen:
                            seen.add(icao)
                            cs = d.get("callsign", "-")
                            alt = d.get("altitude", "-")
                            lat = d.get("lat")
                            lon = d.get("lon")
                            pos = f" [{lat:.4f},{lon:.4f}]" if lat else ""
                            print(f"  [{time.strftime('%H:%M:%S')}] {icao} {cs:>8s} {alt}ft{pos}", flush=True)
                        found += 1
                    except Exception:
                        pass
    except IndexError:
        continue

print(f"\n解码: {found} 条消息, {len(seen)} 架飞机", flush=True)
if not seen:
    print("仍未能解码出有效消息")
