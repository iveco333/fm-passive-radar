#!/usr/bin/env python3
"""1090 MHz 信号质量分析: 前导脉冲形态 + 信噪比"""
import sys, os
import numpy as np
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from sdrplay_api import SDRplayAPI

sdr = SDRplayAPI()
sdr.select_device(0)
sdr.set_frequency(float(sys.argv[1])*1e6 if len(sys.argv)>1 else 1090e6)
sdr.set_sample_rate(2.4e6)
sdr.set_gain(30)
print("capturing 3s...", flush=True)
iq = sdr.capture(3.0)
sdr.close()

mag = np.abs(iq)
# 整体 SNR 估计
signal_power = np.mean(mag**2)
# 找最强区域
p99 = np.percentile(mag, 99)
print(f"\n整体: median={np.median(mag):.4f} p99={p99:.4f} max={mag.max():.4f}")
print(f"动态范围: {20*np.log10(p99/np.median(mag)):.1f} dB (越好越利于解码)")

# 频谱分析 1090 中心 +/- 500kHz
from numpy.fft import fft, fftshift
n_fft = 262144
seg = iq[:n_fft]
spec = 20*np.log10(np.abs(fftshift(fft(seg * np.hanning(n_fft)))) + 1e-12)
freqs = (np.arange(n_fft) - n_fft/2) / n_fft * 2.4e6 / 1e3
# 中心 200kHz 内平均 vs 全带平均
center_mask = np.abs(freqs) < 100
band_mask = np.abs(freqs) < 1000
print(f"\n频谱: 中心±100kHz 均值 {spec[center_mask].mean():.1f} dB")
print(f"      全带±1MHz 均值 {spec[band_mask].mean():.1f} dB")
print(f"      最强分量: {freqs[np.argmax(spec)]:+.0f} kHz @ {spec.max():.1f} dB")

# 找前导脉冲形态 (0,1,2,3.5us)
fs = 2.4e6
bit = int(fs * 1e-6)
thr = p99 * 0.8
above = mag > thr
n = len(mag)
found = 0
for i in range(200, n - 300):
    if not above[i]:
        continue
    try:
        if above[i+bit] and above[i+2*bit] and above[i+int(3.5*bit)]:
            if not above[i+bit//2] and not above[i+bit+bit//2]:
                # 打印前 20 个前导的波形
                if found < 20:
                    seg_mag = mag[i-4:i+int(10*bit)]
                    peaks = [f"{m:.3f}" for m in seg_mag[::4]]
                    print(f"preamble@{i}: {','.join(peaks[:12])}")
                found += 1
    except IndexError:
        continue
print(f"\n检测到 {found} 个前导脉冲模式")
if found == 0:
    print("没有符合 0-1-2-3.5us 模式的前导 -> 信号不是 ADS-B 或 SNR 太低")
