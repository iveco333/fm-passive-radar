#!/usr/bin/env python3
"""1090 诊断: 不同 LO 偏移下的泄漏 vs 信号
判断: LO泄漏是主瓶颈, 还是天线增益不够
"""
import sys, os, time
import numpy as np
import scipy.signal as sig
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from sdrplay_api import SDRplayAPI

FS = 2.375e6
DURATION = 4.0
GAIN = 30

for lo_khz in [250, 500, -250]:
    FREQ = 1090e6 + lo_khz*1e3
    sdr = SDRplayAPI()
    sdr.select_device(0)
    sdr.set_frequency(FREQ)
    sdr.set_sample_rate(2.4e6)
    sdr.set_gain(GAIN)
    iq = sdr.capture(DURATION)
    sdr.close()

    t = np.arange(len(iq)) / FS
    iq_shift = iq * np.exp(-2j * np.pi * lo_khz*1e3 * t)
    b, a = sig.butter(2, 20e3 / (FS/2), 'high')
    iq_dc = sig.filtfilt(b, a, iq_shift)

    mag = np.abs(iq_dc)
    p99 = np.percentile(mag, 99)
    dyn = 20*np.log10(p99/np.median(mag)) if np.median(mag) > 0 else 0
    print(f"\nLO偏移 {lo_khz:+5d}kHz: 动态范围 {dyn:.1f} dB")

    # 频谱
    n_fft = 262144
    spec = 20*np.log10(np.abs(np.fft.fftshift(np.fft.fft(iq_dc[:n_fft]*np.hanning(n_fft))))+1e-12)
    freqs = (np.arange(n_fft)-n_fft/2)/n_fft*FS/1e3
    band = (freqs > -600) & (freqs < 600)
    spec_b, fr_b = spec[band], freqs[band]
    noise = np.median(spec_b)
    idx = np.argsort(spec_b)[-6:][::-1]
    for i in sorted(idx, key=lambda j: fr_b[j]):
        print(f"  {fr_b[i]:+7.1f} kHz  (+{spec_b[i]-noise:5.1f} dB)", flush=True)

    # 前导脉冲
    bit = int(FS*1e-6)
    thr = p99 * 0.8
    above = mag > thr
    n = len(mag)
    preambles = 0
    for i in range(200, n-400):
        if not above[i]: continue
        try:
            if above[i+bit] and above[i+2*bit] and above[i+int(3.5*bit)]:
                if not above[i+bit//2] and not above[i+bit+bit//2] and not above[i+2*bit+bit//2]:
                    preambles += 1
        except IndexError:
            continue
    print(f"  前导脉冲: {preambles} ({DURATION}s)")
    time.sleep(1)
