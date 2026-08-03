#!/usr/bin/env python3
"""Windows 1090 MHz ADS-B 脉冲检测 - RSP1 直驱
检测 1090 MHz 上的 ADS-B 应答脉冲, 评估天线/信号强度
"""
import sys
import os
import time
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from sdrplay_api import SDRplayAPI

FREQ = 1090e6
FS = 2.4e6
GAIN = int(sys.argv[1]) if len(sys.argv) > 1 else 30

sdr = SDRplayAPI()
print("API opened")

sdr.select_device(0)
print("设备选择完成")
sdr.set_frequency(FREQ)
sdr.set_sample_rate(FS)
sdr.set_gain(GAIN)
print(f"已调谐 {FREQ/1e6:.0f} MHz, 采样率 {FS/1e6:.1f} MHz, 增益 {GAIN}")

# 采集几秒数据
CAPTURE_SECS = 3.0
iq = sdr.capture(CAPTURE_SECS)
print(f"采集 {len(iq)} samples ({len(iq)/FS:.1f}s)")

mag = np.abs(iq)
noise = np.median(mag)
print(f"底噪(中位数): {10*np.log10(noise+1e-12):.1f} dBFS")
print(f"峰值: {10*np.log10(mag.max()+1e-12):.1f} dBFS")

# 脉冲检测: 超过底噪 4 倍 (12dB) 的样本
thr = noise * 4.0
n_pulse = int(np.sum(mag > thr))
print(f"脉冲样本数: {n_pulse}")

# 找脉冲串 (连续超过阈值的段)
above = mag > thr
pulses = []
start = None
for i, a in enumerate(above):
    if a and start is None:
        start = i
    elif not a and start is not None:
        if i - start > 2:  # 至少 3 样本才算脉冲
            pulses.append((start, i))
        start = None
if start is not None and len(above) - start > 2:
    pulses.append((start, len(above)))

print(f"检测到 {len(pulses)} 个脉冲串")

if n_pulse > 500:
    print("\n结论: 检测到大量 ADS-B 脉冲! 天线工作良好")
elif n_pulse > 50:
    print("\n结论: 有 ADS-B 信号, 但较弱 (可尝试调整天线)")
elif n_pulse > 0:
    print("\n结论: 信号非常弱, 基本不可用")
else:
    print("\n结论: 未检测到信号")

sdr.close()
