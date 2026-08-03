#!/usr/bin/env python3
"""RSP1 多频段快速扫描 - 找找周围还有什么信号可玩
每段 6MHz 带宽, 0.2s 采样, FFT 找最强峰"""
import sys, os, time
import numpy as np
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from sdrplay_api import SDRplayAPI

FS = 6e6
DURATION = 0.2
GAIN = 40

# (起始MHz, 结束MHz, 标签)
BANDS = [
    (88,  108, "FM 广播"),
    (118, 138, "航空 VHF (塔台/进近)"),
    (137, 139, "气象卫星 APT"),
    (150, 166, "应急/寻呼/铁路"),
    (430, 440, "业余 UHF 段"),
    (460, 470, "对讲机/中继"),
]

def scan(sdr, f_start, f_end):
    rows = []
    f = f_start
    while f < f_end:
        try:
            sdr.set_frequency(f * 1e6)
            iq = sdr.capture(DURATION)
            n = len(iq)
            win = np.hanning(n)
            spec = np.abs(np.fft.fftshift(np.fft.fft(iq * win)))
            spec_db = 20 * np.log10(spec + 1e-12)
            freqs = np.linspace(-FS/2, FS/2, n)
            pk = np.argmax(spec_db)
            pk_freq = f + freqs[pk] / 1e6
            over_noise = spec_db[pk] - np.median(spec_db)
            rows.append((f, pk_freq, over_noise, np.median(spec_db)))
            print(f"  {f:6.1f}MHz: 峰 {pk_freq:9.3f}MHz  (高于噪底 {over_noise:5.1f} dB)", flush=True)
        except Exception as e:
            print(f"  {f:6.1f}MHz: 错误 {e}", flush=True)
        f += 5.0
    return rows

def main():
    sdr = SDRplayAPI()
    sdr.select_device(0)
    sdr.set_sample_rate(FS)
    sdr.set_gain(GAIN)
    print(f"带宽 {FS/1e6:.0f}MHz, 增益 {GAIN}dB, 每段 {DURATION}s\n")

    for f0, f1, label in BANDS:
        print(f"== {label} ({f0}-{f1} MHz) ==", flush=True)
        scan(sdr, f0, f1)
        print(flush=True)

    sdr.close()
    print("扫描完成")

if __name__ == "__main__":
    main()
