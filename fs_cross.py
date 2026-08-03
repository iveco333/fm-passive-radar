#!/usr/bin/env python3
"""BW_0_200 档双假设交叉验证: 同一信号两种假设fs, 导频位置若反比变化 -> 假设错误"""
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

for fs_assumed in [0.25e6, 0.4e6, 0.6e6]:
    spec = np.abs(np.fft.fftshift(np.fft.fft(audio * np.hanning(n))))
    spec_db = 20*np.log10(spec + 1e-12)
    freqs = np.linspace(-fs_assumed/2, fs_assumed/2, n)
    pos = (freqs > 5e3) & (freqs < 30e3)
    band_db = spec_db[pos]
    band_f = freqs[pos]
    pk = np.argmax(band_db)
    f_disp = band_f[pk]
    # 也在全带找最强
    full_pk = np.argmax(spec_db[n//4:3*n//4]) + n//4
    f_full = freqs[full_pk]
    print(f"假设fs={fs_assumed/1e3:.0f}k: 5-30k峰={f_disp/1e3:6.2f}k  全带最强={f_full/1e3:7.2f}k", flush=True)
