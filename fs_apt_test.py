#!/usr/bin/env python3
"""标定 BW_0_200 (250k 请求) 的实际硬件采样率"""
import sys, os, time
import numpy as np
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from sdrplay_api import SDRplayAPI

sdr = SDRplayAPI()
sdr.select_device(0)
sdr.set_sample_rate(250000)   # 和 record_apt_win.py 一样
sdr.set_frequency(137.62e6)
sdr.set_gain(30)

# 录 5 秒, 数实际样本数
t0 = time.time()
iq = sdr.capture(5.0)
elapsed = time.time() - t0
sdr.close()

print(f"请求 250000x5 = 1,250,000 样本")
print(f"实际收到 {len(iq)} 样本, 耗时 {elapsed:.2f}s")
print(f"实际采样率 = {len(iq)/elapsed/1e3:.1f} kSPS")
print(f"=> 若按 250k 假设, 误差 {len(iq)/elapsed/250000*100-100:+.0f}%")
