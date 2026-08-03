#!/usr/bin/env python3
"""1090 MHz 带 LO 偏移 + DC 阻挡的接收测试
调谐到 1090+offset, 基带再移回, 避开 DC/LO泄漏
"""
import sys, os, time
import numpy as np
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from sdrplay_api import SDRplayAPI

FREQ = 1090e6
LO_OFFSET = 200e3  # LO 偏移 200kHz
FS = 2.4e6
GAIN = 30

sdr = SDRplayAPI()
sdr.select_device(0)
sdr.set_frequency(FREQ + LO_OFFSET)
sdr.set_sample_rate(FS)
sdr.set_gain(GAIN)
print(f"LO 偏移调谐: {FREQ/1e6:.0f}+{LO_OFFSET/1e3:.0f} kHz", flush=True)

iq = sdr.capture(3.0)
sdr.close()

# 数字下变频: 移回 1090
t = np.arange(len(iq)) / FS
iq_shift = iq * np.exp(-2j * np.pi * LO_OFFSET * t)

# DC 阻挡 (高通)
from scipy import signal as sp_signal
b, a = sp_signal.butter(2, 20e3 / (FS/2), 'high')
iq_dc = sp_signal.filtfilt(b, a, iq_shift)

mag = np.abs(iq_dc)
p99 = np.percentile(mag, 99)
print(f"DC阻挡后: median={np.median(mag):.4f} p99={p99:.4f} max={mag.max():.4f}")
print(f"动态范围: {20*np.log10(p99/np.median(mag)):.1f} dB")

# 频谱
n_fft = 262144
spec = 20*np.log10(np.abs(np.fft.fftshift(np.fft.fft(iq_dc[:n_fft] * np.hanning(n_fft)))) + 1e-12)
freqs = (np.arange(n_fft) - n_fft/2) / n_fft * FS / 1e3
pk_idx = np.argmax(spec)
print(f"最强分量: {freqs[pk_idx]:+.0f} kHz @ {spec[pk_idx]:.1f} dB")

# 前导检测 + 粗解码
bit = int(FS * 1e-6)
thr = p99 * 0.8
above = mag > thr
n = len(mag)
preambles = 0
for i in range(200, n - 300):
    if not above[i]:
        continue
    try:
        if above[i+bit] and above[i+2*bit] and above[i+int(3.5*bit)]:
            if not above[i+bit//2] and not above[i+bit+bit//2]:
                preambles += 1
    except IndexError:
        continue
print(f"前导脉冲: {preambles}")

# 保存处理后的 IQ 供进一步解码
iq_dc[:2000000].astype(np.complex64).tofile(os.path.join(os.path.dirname(os.path.abspath(__file__)), "adsb_lo_shift.bin"))
print("已保存 200 万样本 adsb_lo_shift.bin")
