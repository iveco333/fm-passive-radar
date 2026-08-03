#!/usr/bin/env python3
"""用 88MHz 19kHz 导频标定 BW_0_200 (APT 档位) 的实际采样率"""
import sys, os
import numpy as np
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from sdrplay_api import SDRplayAPI

sdr = SDRplayAPI()
sdr.select_device(0)
sdr.set_sample_rate(0.25e6)   # APT 用的请求值 -> BW_0_200
sdr.set_frequency(88e6)
sdr.set_gain(40)
iq = sdr.capture(4.0)
sdr.close()

audio = np.diff(np.unwrap(np.angle(iq)))
audio = audio - np.mean(audio)
n = len(audio)
spec = np.abs(np.fft.fftshift(np.fft.fft(audio * np.hanning(n))))
spec_db = 20*np.log10(spec + 1e-12)
fs_assumed = 0.25e6
freqs = np.linspace(-fs_assumed/2, fs_assumed/2, n)
pos = (freqs > 10e3) & (freqs < 30e3)
pk = np.argmax(spec_db[pos])
f_disp = freqs[pos][pk]
fs_real = fs_assumed * 19e3 / f_disp
print(f"19k 导频显示: {f_disp/1e3:.3f} kHz")
print(f"=> 实际采样率: {fs_real/1e3:.1f} kSPS")
