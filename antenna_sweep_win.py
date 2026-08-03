#!/usr/bin/env python3
"""天线频率响应扫描: 从 20MHz 到 1.6GHz, 检测各频段噪声/信号水平
反映天线在不同频率的接收效率
"""
import sys, os, time
import numpy as np
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from sdrplay_api import SDRplayAPI

FS = 2.4e6
GAIN = 30

sdr = SDRplayAPI()
sdr.select_device(0)
sdr.set_sample_rate(FS)
sdr.set_gain(GAIN)

# 扫描频点 (MHz): 低频稀疏, 高频加密
points = []
# 20-100 MHz: 每 5 MHz
points += list(np.arange(20, 100, 5))
# 100-500 MHz: 每 10 MHz
points += list(np.arange(100, 500, 10))
# 500-1000 MHz: 每 20 MHz
points += list(np.arange(500, 1000, 20))
# 1000-1600 MHz: 每 25 MHz
points += list(np.arange(1000, 1600, 25))

buf_len = 131072
results = []

for f in points:
    try:
        sdr.set_frequency(f * 1e6)
        time.sleep(0.25)
        # 用底层方法采一段
        iq = sdr.capture(0.2)
        if len(iq) < 1000:
            results.append((f, None, None))
            continue
        mag = np.abs(iq)
        noise = 10*np.log10(np.median(mag) + 1e-12)
        peak = 10*np.log10(np.percentile(mag, 99.9) + 1e-12)
        results.append((f, noise, peak))
    except Exception as e:
        results.append((f, None, None))

sdr.close()

print(f"\n{'频率 MHz':>10} {'底噪 dBFS':>12} {'峰值 dBFS':>12}  信号")
for f, noise, peak in results:
    if noise is None:
        print(f"{f:10.0f} {'ERR':>12} {'':>12}")
        continue
    sig = peak - noise
    bar = '#' * max(0, int(sig * 2))
    mark = "  <-- 有信号" if sig > 15 else ""
    print(f"{f:10.0f} {noise:12.1f} {peak:12.1f}  {bar}{mark}")

# 汇总: 找信号活跃频段
print("\n=== 信号活跃频段 (peak-noise > 15dB) ===")
active = [(f, p-n) for f, n, p in results if n is not None and p is not None and (p-n) > 15]
for f, s in active:
    print(f"  {f:.0f} MHz (+{s:.1f} dB)")
if not active:
    print("  无")
