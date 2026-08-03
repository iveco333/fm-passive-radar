#!/usr/bin/env python3
"""补扫 400-430MHz (公众对讲机 409 / 行业段 410-430) + 交叉验证"""
import sys, os
import numpy as np
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from sdrplay_api import SDRplayAPI

FS = 6e6
DURATION = 0.6
GAIN = 40
TUNES = [400.0, 405.0, 410.0, 415.0, 420.0, 425.0]

def get_peaks(iq, fs, k=8, min_over=8):
    n = len(iq)
    win = np.hanning(n)
    spec = np.abs(np.fft.fftshift(np.fft.fft(iq * win)))
    spec_db = 20 * np.log10(spec + 1e-12)
    freqs = np.linspace(-fs/2, fs/2, n)
    noise = np.median(spec_db)
    out = []
    s = spec_db.copy()
    for _ in range(k):
        pk = np.argmax(s)
        if s[pk] - noise < min_over:
            break
        p = pk
        if 1 < p < len(s)-1:
            d = (s[p-1] - s[p+1]) / (2*(s[p-1] - 2*s[p] + s[p+1] + 1e-12))
            fp = freqs[p] + d * (freqs[1]-freqs[0])
        else:
            fp = freqs[p]
        out.append((fp, s[p] - noise))
        s[max(0,p-40):p+40] = -999
    return out

def main():
    sdr = SDRplayAPI()
    sdr.select_device(0)
    sdr.set_sample_rate(FS)
    sdr.set_gain(GAIN)

    all_peaks = []
    for t in TUNES:
        sdr.set_frequency(t * 1e6)
        iq = sdr.capture(DURATION)
        pks = get_peaks(iq, FS)
        line = []
        for off, ov in pks:
            phys = t + off/1e6
            line.append(f"{phys:8.3f}M({ov:+.0f})")
            all_peaks.append((t, phys, ov))
        print(f"调谐 {t:6.1f}M: " + "  ".join(line), flush=True)

    print("\n== 真实信号候选 (跨调谐一致) ==", flush=True)
    seen = {}
    for t, phys, ov in all_peaks:
        key = round(phys * 1000)
        found = False
        for k in range(key-60, key+61):
            if k in seen:
                seen[k].append((t, phys, ov))
                found = True
                break
        if not found:
            seen[key] = [(t, phys, ov)]
    n_hits = 0
    for k, v in sorted(seen.items()):
        if len(v) >= 2:
            freqs = set(round(x[1], 3) for x in v)
            if len(freqs) == 1:
                n_hits += 1
                print(f"  {k/1000:8.3f} MHz  出现{len(v)}次: " + ", ".join(f"t={t}M +{ov:.0f}dB" for t, _, ov in v))
    if n_hits == 0:
        print("  无")
    sdr.close()

if __name__ == "__main__":
    main()
