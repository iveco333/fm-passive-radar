#!/usr/bin/env python3
"""校准 + 航空频段精细扫描
1) 88MHz 用不同带宽对比, 验证频率轴标定
2) 航空 118-137MHz 以 1MHz 步进, 1.536MHz 带宽, 找窄带信号"""
import sys, os, time
import numpy as np
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from sdrplay_api import SDRplayAPI

def peaks(iq, fs, k=5):
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
        if s[pk] - noise < 10:
            break
        out.append((freqs[pk]/1e6, s[pk] - noise))
        s[max(0,pk-50):pk+50] = -999
    return out, noise

def main():
    sdr = SDRplayAPI()
    sdr.select_device(0)
    sdr.set_gain(40)

    # --- 校准: 88MHz 两种带宽对比 ---
    print("== 校准: 88 MHz ==", flush=True)
    for fs, label in [(1.94e6, "BW_1_536 (~1.94M)"), (6e6, "BW_6_000 (~6M)")]:
        sdr.set_sample_rate(fs)
        sdr.set_frequency(88e6)
        iq = sdr.capture(0.3)
        pks, noise = peaks(iq, fs, 6)
        print(f"  {label}: 噪底 {noise:.0f}dB", flush=True)
        for f, o in pks:
            print(f"    峰 {88+f:9.3f}MHz  (偏移 {f:+.3f}MHz, +{o:.1f}dB)", flush=True)

    # --- 航空段精细扫描 ---
    print("\n== 航空 VHF 118-137 MHz 精细扫描 ==", flush=True)
    sdr.set_sample_rate(1.94e6)
    hits = []
    f = 118.0
    while f < 137.0:
        sdr.set_frequency(f * 1e6)
        iq = sdr.capture(0.4)
        pks, noise = peaks(iq, 1.94e6, 3)
        line = []
        for pf, ov in pks:
            line.append(f"{f+pf:8.3f}MHz(+{ov:.0f}dB)")
            if ov > 15:
                hits.append((f + pf, ov))
        print(f"  {f:6.1f}MHz: {'  '.join(line) if line else '(无)'}", flush=True)
        f += 1.0

    print("\n== 汇总: 强窄带信号 ==", flush=True)
    for hf, hv in sorted(hits):
        print(f"  {hf:8.3f} MHz  (+{hv:.0f} dB)", flush=True)
    sdr.close()

if __name__ == "__main__":
    main()
