#!/usr/bin/env python3
"""最终验证: BW_0_200 档真实采样率. 请求 0.25e6, 在不同假设fs下找峰, 反推归一化位置"""
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

# 用归一化频率找峰 (不依赖假设fs): 找 0.004-0.02 归一化区间的峰 (对应 8k-40k @ 2M)
spec = np.abs(np.fft.fftshift(np.fft.fft(audio * np.hanning(n))))
spec_db = 20*np.log10(spec + 1e-12)
norm_freqs = np.linspace(-0.5, 0.5, n)  # 归一化频率 (cycles/sample)

print("归一化频率最强峰 (全带):")
noise = np.median(spec_db)
for lo, hi in [(0.004, 0.03)]:
    pos = (norm_freqs > lo) & (norm_freqs < hi)
    idx = np.argsort(spec_db[pos])[-8:][::-1]
    print(f"  [{lo:.3f}-{hi:.3f}]")
    for i in sorted(idx, key=lambda j: norm_freqs[pos][j]):
        nf = norm_freqs[pos][i]
        print(f"    norm={nf:.5f}  (+{spec_db[pos][i]-noise:5.1f}dB)  "
              f"若fs=2.0M→{nf*2.0e6/1e3:6.2f}k  若fs=2.375M→{nf*2.375e6/1e3:6.2f}k", flush=True)

# 反推: 若 19k 导频在 norm_f, 则 fs_real = 19e3/norm_f
print("\n反推: 19k 导频候选 norm 值:")
cands = [0.0095, 0.0080, 0.0152]
for c in cands:
    print(f"  norm={c} -> fs_real={19e3/c/1e6:.3f}M")
