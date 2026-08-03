#!/usr/bin/env python3
"""NOAA 天线测试: 测 137.9125 MHz (NOAA18) 底噪 - 带天线 vs 无天线对比
用法: python noaa_noise_floor.py <label>
"""
import sys, os
import numpy as np
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from sdrplay_api import SDRplayAPI

FS = 2.375e6
GAIN = 40
FREQ = 137.9125e6   # NOAA18 APT 下行

def main():
    label = sys.argv[1] if len(sys.argv) > 1 else "test"
    sdr = SDRplayAPI()
    sdr.select_device(0)
    sdr.set_sample_rate(FS)
    sdr.set_frequency(FREQ)
    sdr.set_gain(GAIN)
    iq = sdr.capture(5.0)
    sdr.close()
    n = len(iq)
    win = np.hanning(n)
    spec = np.abs(np.fft.fftshift(np.fft.fft(iq * win)))
    spec_db = 20 * np.log10(spec + 1e-12)
    noise = np.median(spec_db)
    s = spec_db.copy()
    nzc = len(s)//2
    s[nzc-5:nzc+5] = -999  # 屏蔽 DC
    pk = np.argmax(s)
    freqs = np.linspace(-FS/2, FS/2, n)
    print(f"[{label}] 137.9125MHz 底噪: {noise:.1f} dBFS | "
          f"最强峰: {FREQ/1e6 + freqs[pk]/1e6:.4f} MHz (+{s[pk]-noise:.1f}dB)", flush=True)

if __name__ == "__main__":
    main()
