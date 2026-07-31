#!/usr/bin/env python3
"""
ADS-B Receiver -- RSP1 on Windows

Captures 1090 MHz, decodes Mode S/ADS-B frames via pyModeS v3.x,
displays aircraft.

Deps: pip install pymodes numpy
"""

import sys
import os
import time
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import pyModeS as pms

FREQ = 1090e6
FS = 2.4e6
GAIN = 30
CAPTURE_SECS = 1.0

BIT_SAMPLES = int(FS * 1e-6)
PREAMBLE_SAMPLES = [int(p * FS * 1e-6) for p in [0, 1.0, 2.0, 3.5]]
SHORT_FRAME_BITS = 56
LONG_FRAME_BITS = 112


def magnitude(iq):
    return np.abs(iq)


def dc_block(x, alpha=0.01):
    y = np.zeros_like(x)
    dc = 0.0
    for i in range(len(x)):
        dc += alpha * (x[i] - dc)
        y[i] = x[i] - dc
    return y


def find_preamble(sig, thresh=0.12):
    n = len(sig)
    s = sig / (np.median(np.abs(sig)) + 1e-10)
    peaks = []
    half = BIT_SAMPLES // 2

    for i in range(50, n - 150):
        if s[i] <= s[i - 1] or s[i] <= s[i + 1]:
            continue
        if s[i] < thresh:
            continue

        p1 = i + PREAMBLE_SAMPLES[1]
        p2 = i + PREAMBLE_SAMPLES[2]
        p3 = i + PREAMBLE_SAMPLES[3]
        if p3 >= n - 10:
            break

        m = [s[i], s[p1], s[p2], s[p3]]
        n0 = s[i + half]
        n1 = s[p1 + half]
        n2 = s[p2 + half]
        n3_pos = i + int(FS * 3.0e-6)
        n3 = s[n3_pos] if n3_pos < n else 0

        if (m[0] > n0 * 1.3 and m[1] > n1 * 1.3 and
                m[2] > n2 * 1.3 and m[3] > n3 * 1.3):
            peaks.append(i)

    return peaks


def decode_bits(sig, start, n_bits):
    pos = start + PREAMBLE_SAMPLES[-1] + 4 * BIT_SAMPLES
    bits = []
    half = BIT_SAMPLES // 2
    for i in range(n_bits):
        p = pos + i * BIT_SAMPLES
        if p + BIT_SAMPLES >= len(sig):
            return None
        e1 = np.sum(sig[p:p + half])
        e2 = np.sum(sig[p + half:p + BIT_SAMPLES])
        bits.append(1 if e1 > e2 else 0)
    return bits


def bits_to_hex(bits):
    val = 0
    for b in bits:
        val = (val << 1) | b
    hex_str = hex(val)[2:].upper().zfill(len(bits) // 4)
    return hex_str


def try_decode(sig, start):
    bits = decode_bits(sig, start, LONG_FRAME_BITS)
    if bits is None:
        return None
    hex_str = bits_to_hex(bits)
    if len(hex_str) != 28:
        return None

    try:
        m = pms.Message(hex_str)
        if not m.crc_valid:
            bits2 = decode_bits(sig, start, SHORT_FRAME_BITS)
            if bits2:
                h2 = bits_to_hex(bits2)
                if len(h2) == 14:
                    try:
                        m2 = pms.Message(h2)
                        if m2.crc_valid:
                            m = m2
                            hex_str = h2
                    except Exception:
                        pass
        if not m.crc_valid:
            return None
    except Exception:
        return None

    try:
        d = m.decode()
        info = {
            "hex": hex_str,
            "icao": d.get("icao", ""),
            "tc": d.get("typecode"),
            "callsign": (d.get("callsign", "") or "").strip("_# "),
            "altitude": d.get("altitude"),
            "velocity": d.get("velocity"),
            "heading": d.get("heading"),
            "vert_rate": d.get("vertical_rate"),
        }
        if d.get("has_position"):
            info["lat"] = d.get("lat")
            info["lon"] = d.get("lon")
        return info
    except Exception:
        return None


def process_cycle(iq):
    sig = magnitude(iq)
    sig = dc_block(sig)
    starts = find_preamble(sig)
    frames = []
    seen = set()
    for s in starts:
        info = try_decode(sig, s)
        if info and info.get("hex") not in seen:
            seen.add(info["hex"])
            frames.append(info)
    return frames


def main():
    from sdrplay_api import SDRplayAPI

    print("=" * 55)
    print("ADS-B Receiver  --  RSP1 @ 1090 MHz")
    print("=" * 55)

    seen_icao = {}
    total_msgs = 0
    cycle = 0

    with SDRplayAPI() as sdr:
        sdr.select_device(0)
        sdr.set_frequency(FREQ)
        sdr.set_sample_rate(FS)
        sdr.set_gain(GAIN)
        print(f"  RX: 1090 MHz  {FS/1e6:.1f} MSPS  gain={GAIN}")
        print("  Waiting for aircraft... (Ctrl+C to stop)")
        print()

        while True:
            cycle += 1
            iq = sdr.capture(CAPTURE_SECS)
            frames = process_cycle(iq)

            for f in frames:
                icao = f.get("icao", f.get("hex", "?"))
                total_msgs += 1
                is_new = icao not in seen_icao
                seen_icao[icao] = f

                if is_new:
                    cs = (f.get("callsign") or "---")[:8]
                    alt = f.get("altitude") or "---"
                    spd = f.get("velocity") or "---"
                    hdg = f.get("heading") or "---"
                    lat = f.get("lat")
                    lon = f.get("lon")
                    pos = f" [{lat:.4f},{lon:.4f}]" if lat else ""
                    ts = time.strftime("%H:%M:%S")
                    alt_s = str(alt) if isinstance(alt, str) else f"{alt}ft"
                    print(f"  [{ts}] {icao} {cs:>8s} {alt_s:>7} {spd:>3}kt {hdg:>3}deg{pos}")

            if frames:
                n_ac = len(seen_icao)
                print(f"  -- cycle {cycle}: {len(frames)} msgs ({total_msgs}) {n_ac} acft --")
            elif cycle % 10 == 0:
                n_ac = len(seen_icao)
                print(f"  -- listening... ({n_ac} acft) --")

    print(f"\nTotal: {len(seen_icao)} aircraft ({total_msgs} msgs)")
    for icao, f in sorted(seen_icao.items()):
        cs = (f.get("callsign") or "")[:8]
        alt = f.get("altitude") or "?"
        spd = f.get("velocity") or "?"
        lat = f.get("lat")
        lon = f.get("lon")
        pos = f" [{lat:.4f},{lon:.4f}]" if lat else ""
        print(f"  {icao}  {cs:8s}  {alt}ft  {spd}kt{pos}")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\nStopped.")
    except Exception as e:
        import traceback
        traceback.print_exc()
