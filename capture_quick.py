#!/usr/bin/env python3
"""快速 capture 验证 + 脉冲统计"""
import sys, os, time
import numpy as np
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from sdrplay_api import SDRplayAPI

sdr = SDRplayAPI()
sdr.select_device(0)
sdr.set_frequency(1090e6)
sdr.set_sample_rate(2.4e6)
sdr.set_gain(30)
print("RX ready, capturing 2s...", flush=True)
iq = sdr.capture(2.0)
print(f"captured {len(iq)}", flush=True)
mag = np.abs(iq)
print(f"median {np.median(mag):.4f}  p99 {np.percentile(mag,99):.4f}  max {mag.max():.4f}", flush=True)
# 找脉冲: 超过 p99*1.5
thr = np.percentile(mag, 99) * 1.5
above = mag > thr
print(f"pulses: {int(above.sum())} samples", flush=True)
sdr.close()
print("done", flush=True)
