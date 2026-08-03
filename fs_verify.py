#!/usr/bin/env python3
"""验证: 假设 fs=622k 时 19k 导频应显示 19k, 38k 副载波应显示 38k"""
import sys, os
import numpy as np
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from sdrplay_api import SDRplayAPI

sdr = SDRplayAPI()
sdr.select_device(0)
sdr.set_sample_rate(0.25e6)   # BW_0_200
sdr.set_frequency(88e6)
sdr.set_gain(40)
iq = sdr.capture(4.0)
sdr.close()

audio = np.diff(np.unwrap(np.angle(iq)))
audio = audio - np.mean(audio)
n = len(audio)

for fs_assumed in [0.622e6, 0.30e6]:
    spec = np.abs(np.fft.fftshift(np.fft.fft(audio * np.hanning(n))))
    spec_db = 20*np.log10(spec + 1e-12)
    freqs = np.linspace(-fs_assumed/2, fs_assumed/2, n)
    # 找 0-60k 所有显著峰
    pos = (freqs > 0) & (freqs < 60e3)
    band_db = spec_db[pos]
    band_f = freqs[pos]
    noise = np.median(spec_db)
    idx = np.argsort(band_db)[-6:][::-1]
    print(f"假设fs={fs_assumed/1e3:.0f}k: 最强峰:")
    for i in sorted(idx, key=lambda j: band_f[j]):
        print(f"  {band_f[i]/1e3:6.2f}k  (+{band_db[i]-noise:5.1f}dB)", flush=True)
