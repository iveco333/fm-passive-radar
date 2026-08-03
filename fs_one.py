#!/usr/bin/env python3
"""分段测 bwType 实际采样率 (一次一个点, 防服务崩溃)"""
import sys, os, time
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import sdrplay_api as sa

req = float(sys.argv[1])
print(f"--- 请求 {req/1e3:.0f} kHz ---", flush=True)
sdr = sa.SDRplayAPI()
sdr.select_device(0)
sdr.set_sample_rate(req)
sdr.set_frequency(137.62e6)
sdr.set_gain(30)
t0 = time.time()
iq = sdr.capture(3.0)
elapsed = time.time() - t0
sdr.close()
fs = len(iq) / elapsed if elapsed > 0 else 0
print(f"样本 {len(iq)}, 耗时 {elapsed:.2f}s, 实际 {fs/1e3:.1f} kSPS", flush=True)
