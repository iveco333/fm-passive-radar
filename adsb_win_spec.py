#!/usr/bin/env python3
"""Windows 1090 MHz 频谱分析 - 区分 ADS-B 脉冲 vs 持续干扰"""
import sys
import os
import time
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from sdrplay_api import SDRplayAPI

FREQ = 1090e6
FS = 2.4e6
GAIN = 10

sdr = SDRplayAPI()
sdr.select_device(0)
sdr.set_frequency(FREQ)
sdr.set_sample_rate(FS)
sdr.set_gain(GAIN)
print(f"调谐 {FREQ/1e6:.0f} MHz, 增益 {GAIN}")

iq = sdr.capture(2.0)
print(f"采集 {len(iq)} samples")

# 幅度统计
mag = np.abs(iq)
print(f"\n幅度统计:")
print(f"  中位数: {np.median(mag):.4f}")
print(f"  99分位: {np.percentile(mag, 99):.4f}")
print(f"  最大值: {mag.max():.4f}")
print(f"  >0.5 (饱和区): {np.mean(mag>0.5)*100:.1f}%")

# 频谱: 看是宽带噪声还是窄带载波
win = np.hanning(len(iq[:len(iq)//8*8]))
spec = np.abs(np.fft.fftshift(np.fft.fft(iq[:len(iq)//8*8] * win)))
spec_db = 20*np.log10(spec + 1e-12)
freqs = np.linspace(-FS/2, FS/2, len(spec)) / 1e3  # kHz

# 找峰值频率
pk_idx = np.argmax(spec_db)
print(f"\n频谱峰值: {freqs[pk_idx]:+.0f} kHz 偏移, {spec_db[pk_idx]:.1f} dB")
print(f"频谱均值: {np.mean(spec_db):.1f} dB")
print(f"峰值-均值: {spec_db[pk_idx]-np.mean(spec_db):.1f} dB")

if spec_db[pk_idx] - np.mean(spec_db) > 20:
    print("\n结论: 存在强窄带载波 (疑似干扰/镜像, 不是ADS-B)")
elif np.mean(mag > 0.5) * 100 < 1:
    print("\n结论: 无饱和, 信号正常")
else:
    print("\n结论: 宽带高电平 (疑似强干扰)")

# 保存 IQ 供进一步分析
iq[:100000].astype(np.complex64).tofile(os.path.join(os.path.dirname(os.path.abspath(__file__)), "adsb_win_iq.bin"))
print("已保存 10 万样本到 adsb_win_iq.bin")

sdr.close()
