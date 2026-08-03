#!/usr/bin/env python3
"""137MHz 天线效率测试: 细扫 136-138MHz + 88/400MHz 对照
判断羊角天线在 137MHz 是否有接收效率 (对比底噪水平)
"""
import sys, os, time
import numpy as np
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from sdrplay_api import SDRplayAPI

FS = 2.4e6
GAIN = 40  # 和被动雷达一致的增益

sdr = SDRplayAPI()
sdr.select_device(0)
sdr.set_sample_rate(FS)
sdr.set_gain(GAIN)

def measure(f_mhz, dur=0.3):
    sdr.set_frequency(f_mhz * 1e6)
    time.sleep(0.3)
    iq = sdr.capture(dur)
    if len(iq) < 1000:
        return None, None
    mag = np.abs(iq)
    noise = 10*np.log10(np.median(mag) + 1e-12)
    peak = 10*np.log10(np.percentile(mag, 99.99) + 1e-12)
    return noise, peak

print("=" * 60)
print(" 天线效率测试 (gRdB=40)")
print("=" * 60)

# 1. 对照频点: 88MHz FM / 400MHz UHF / 137MHz NOAA
print("\n--- 对照频点 ---")
for f in [88.0, 137.1, 137.62, 137.9125, 400.0]:
    n, p = measure(f)
    if n is None:
        print(f"{f:8.1f} MHz  ERR")
        continue
    sig = p - n
    bar = '#' * max(0, int(sig * 3))
    print(f"{f:8.1f} MHz  底噪{n:6.1f} dBFS  峰值{p:6.1f} dBFS  (+{sig:.1f}dB) {bar}")

# 2. 136-138 细扫 (每 0.05MHz)
print("\n--- 136-138 MHz 细扫 ---")
freqs = np.arange(136.0, 138.05, 0.05)
print(f"{'MHz':>8} {'底噪':>8} {'峰值':>8}  信号")
for f in freqs:
    n, p = measure(f, dur=0.2)
    if n is None:
        print(f"{f:8.2f}  ERR")
        continue
    sig = p - n
    bar = '#' * max(0, int(sig * 3))
    mark = "  <-- 活跃" if sig > 12 else ""
    print(f"{f:8.2f} {n:8.1f} {p:8.1f}  {bar}{mark}")

# 3. 加长监听 NOAA 19 频率 (137.1) 5s, 看有没有 APT 特征 (过境时才可能有)
print("\n--- 监听 137.1 MHz 5s (NOAA19/南美NOAA下行) ---")
n, p = measure(137.1, dur=5.0)
if n is not None:
    print(f"底噪 {n:.1f} dBFS, 峰值 {p:.1f} dBFS (+{p-n:.1f}dB)")
    print("(非过境时段, 正常情况下只有噪声底, 用于确认天线底噪水平)")

sdr.close()
print("\n完成")
