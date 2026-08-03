#!/usr/bin/env python3
"""航空段交叉验证扫描: 跨调谐点位置不变的峰才是真实信号
杂散跟随 LO 移动(固定显示偏移), 真实信号在射频域固定"""
import sys, os
import numpy as np
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from sdrplay_api import SDRplayAPI

FS = 6e6
DURATION = 0.5
GAIN = 40
TUNES = [118.0, 122.0, 126.0, 130.0, 134.0]  # MHz

def get_peaks(iq, fs, k=8, min_over=10):
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
        # 峰频率(抛物线插值)
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

    all_peaks = []  # (调谐, 物理频率MHz, 强度)
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

    print("\n== 跨调谐点一致的峰 (真实信号候选) ==", flush=True)
    # 找: 物理频率在多个调谐点都出现(±50kHz)
    seen = {}
    for t, phys, ov in all_peaks:
        key = round(phys * 1000)  # kHz
        found = False
        for k in range(key-50, key+51):
            if k in seen:
                seen[k].append((t, phys, ov))
                found = True
                break
        if not found:
            seen[key] = [(t, phys, ov)]
    for k, v in sorted(seen.items()):
        if len(v) >= 2:
            freqs = set(round(x[1], 4) for x in v)
            if len(freqs) == 1:  # 位置完全一致
                print(f"  {k/1000:8.3f} MHz  出现{len(v)}次: " + ", ".join(f"t={t}M +{ov:.0f}dB" for t, _, ov in v))
    sdr.close()

if __name__ == "__main__":
    main()
