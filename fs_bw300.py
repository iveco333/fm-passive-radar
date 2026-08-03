#!/usr/bin/env python3
"""测 BW_0_300 实际采样率: 88MHz 台 19kHz 导频法"""
import sys, os
import numpy as np
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from sdrplay_api import SDRplayAPI

sdr = SDRplayAPI()
sdr.select_device(0)
sdr.set_sample_rate(0.3e6)   # BW_0_300
sdr.set_frequency(88e6)
sdr.set_gain(40)
iq = sdr.capture(4.0)
sdr.close()

audio = np.diff(np.unwrap(np.angle(iq)))
audio = audio - np.mean(audio)
n = len(audio)
seg = audio * np.hanning(n)
spec = np.abs(np.fft.fftshift(np.fft.fft(seg)))
spec_db = 20*np.log10(spec + 1e-12)
freqs = np.linspace(-0.3e6/2, 0.3e6/2, n)  # 假设 0.3M
pos = (freqs > 10e3) & (freqs < 30e3)
pk = np.argmax(spec_db[pos])
f_disp = freqs[pos][pk]
print(f"19k 导频显示: {f_disp/1e3:.3f} kHz")
print(f"=> 实际采样率: {0.3e6 * 19e3 / f_disp / 1e6:.4f} MSPS")
