#!/usr/bin/env python3
"""标定被动雷达配置 (请求 2.4e6 -> BW_1_536) 的实际采样率
用 88MHz FM 19kHz 导频 + 38k 副载波交叉验证"""
import sys, os
import numpy as np
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from sdrplay_api import SDRplayAPI

sdr = SDRplayAPI()
sdr.select_device(0)
sdr.set_sample_rate(2.4e6)   # 被动雷达的请求值 -> BW_1_536
sdr.set_frequency(88e6)
sdr.set_gain(40)
iq = sdr.capture(4.0)
sdr.close()

audio = np.diff(np.unwrap(np.angle(iq)))
audio = audio - np.mean(audio)
n = len(audio)
spec = np.abs(np.fft.fftshift(np.fft.fft(audio * np.hanning(n))))
spec_db = 20*np.log10(spec + 1e-12)

# 归一化频率找峰
norm_freqs = np.linspace(-0.5, 0.5, n)
print("0-0.05 归一化区间最强峰:")
noise = np.median(spec_db)
pos = (norm_freqs > 0.002) & (norm_freqs < 0.05)
idx = np.argsort(spec_db[pos])[-8:][::-1]
for i in sorted(idx, key=lambda j: norm_freqs[pos][j]):
    nf = norm_freqs[pos][i]
    print(f"  norm={nf:.5f} (+{spec_db[pos][i]-noise:5.1f}dB)  "
          f"若fs=2.0M→{nf*2.0e6/1e3:6.2f}k  若fs=2.375M→{nf*2.375e6/1e3:6.2f}k")

# 反推: 19k 导频 + 38k 副载波
print("\n反推:")
for cand_norm, label in [(0.0095, '19k@2.0M'), (0.0080, '19k@2.375M'), (0.0190, '38k@2.0M'), (0.0160, '38k@2.375M')]:
    print(f"  {label}: norm={cand_norm}")
