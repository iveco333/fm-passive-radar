#!/usr/bin/env python3
"""蜂窝频段扫描: 920-980MHz (GSM900/LTE B8 下行) + 1800-1880 (LTE B3/GSM1800)
特征: 基站持续发射 → 频段平均功率抬升 / GSM 200kHz 窄带载波"""
import sys, os
import numpy as np
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from sdrplay_api import SDRplayAPI

FS = 6e6
DURATION = 0.4
GAIN = 40

def scan(sdr, f0, f1, step=4.0):
    rows = []
    f = f0
    while f < f1:
        sdr.set_frequency(f * 1e6)
        iq = sdr.capture(DURATION)
        mag = np.abs(iq)
        lvl = 20*np.log10(np.median(mag) + 1e-12)
        n = len(iq)
        spec = np.abs(np.fft.fftshift(np.fft.fft(iq * np.hanning(n))))
        spec_db = 20*np.log10(spec + 1e-12)
        rows.append((f, lvl, np.median(spec_db)))
        print(f"  {f:6.1f}MHz: 中位电平 {lvl:5.1f} dB  频谱中位 {np.median(spec_db):5.1f} dB", flush=True)
        f += step
    return rows

def main():
    sdr = SDRplayAPI()
    sdr.select_device(0)
    sdr.set_sample_rate(FS)
    sdr.set_gain(GAIN)

    print("== GSM900 / LTE B8 下行 (935-960MHz) ==", flush=True)
    r1 = scan(sdr, 920.0, 980.0)
    print(flush=True)
    print("== GSM1800 / LTE B3 下行 (1805-1880MHz) ==", flush=True)
    r2 = scan(sdr, 1795.0, 1885.0, 5.0)

    # 对比: 蜂窝频段 vs 非蜂窝频段
    print("\n== 能量对比 ==", flush=True)
    def band_avg(rows, lo, hi):
        vals = [lvl for f, lvl, _ in rows if lo <= f < hi]
        return np.mean(vals) if vals else float('nan')

    gsm_lo = band_avg(r1, 920, 935)    # 非蜂窝 (参考)
    gsm_hi = band_avg(r1, 935, 960)    # 蜂窝下行
    print(f"920-935MHz (参考):   {gsm_lo:.1f} dB")
    print(f"935-960MHz (蜂窝):   {gsm_hi:.1f} dB  (差 {gsm_hi-gsm_lo:+.1f} dB)", flush=True)
    lte_lo = band_avg(r2, 1795, 1805)  # 非蜂窝
    lte_hi = band_avg(r2, 1805, 1880)  # 蜂窝
    print(f"1795-1805MHz (参考): {lte_lo:.1f} dB")
    print(f"1805-1880MHz (蜂窝): {lte_hi:.1f} dB  (差 {lte_hi-lte_lo:+.1f} dB)", flush=True)
    sdr.close()

if __name__ == "__main__":
    main()
