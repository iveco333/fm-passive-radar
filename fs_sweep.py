#!/usr/bin/env python3
"""批量测各 bwType 请求下的实际硬件采样率"""
import sys, os, time
import numpy as np
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import sdrplay_api as sa

def measure(req_rate):
    sdr = sa.SDRplayAPI()
    sdr.select_device(0)
    sdr.set_sample_rate(req_rate)   # 内部选 bwType
    sdr.set_frequency(137.62e6)
    sdr.set_gain(30)
    t0 = time.time()
    iq = sdr.capture(3.0)
    elapsed = time.time() - t0
    sdr.close()
    fs_actual = len(iq) / elapsed if elapsed > 0 else 0
    return len(iq), elapsed, fs_actual

print(f"{'请求(kHz)':>10} {'bwType':>10} {'样本数':>10} {'耗时(s)':>8} {'实际(kSPS)':>12}")
for req in [100e3, 250e3, 300e3, 500e3, 600e3, 1e6, 1.536e6, 2e6, 2.4e6, 6e6, 8e6]:
    try:
        n, el, fs = measure(req)
        bw = {0: 'BW_0_200', 1: 'BW_0_300', 2: 'BW_0_600', 3: 'BW_1_536', 4: 'BW_5_000', 5: 'BW_6_000', 6: 'BW_8_000'}.get(req <= 0.3e6 and 0 or (req <= 0.6e6 and 1 or (req <= 1.6e6 and 2 or (req <= 6e6 and 3 or 5))), '?')
        print(f"{req/1e3:10.0f} {bw:>10} {n:10d} {el:8.2f} {fs/1e3:12.1f}")
    except Exception as e:
        print(f"{req/1e3:10.0f} {'ERR':>10} {str(e)[:60]}")
    time.sleep(1)
