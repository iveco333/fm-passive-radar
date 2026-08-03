#!/usr/bin/env python3
"""实验: 直接设置 fsFreq.fsHz = 250000, 看是否能真正改变采样率"""
import sys, os, time
import numpy as np
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import sdrplay_api as sa

sdr = sa.SDRplayAPI()
sdr.select_device(0)

devp = sdr.params.devParams.contents
print(f"默认 fsHz: {devp.fsFreq.fsHz}")
devp.fsFreq.fsHz = 250000.0
print(f"设置 fsHz = {devp.fsFreq.fsHz}")

sdr.set_frequency(137.62e6)
sdr.ch.tunerParams.bwType = sa.BW_0_200
sdr.set_gain(30)

t0 = time.time()
iq = sdr.capture(5.0)   # 请求 250000*5 = 1.25M 样本
elapsed = time.time() - t0
sdr.close()

n_req = int(250000 * 5.0)
print(f"请求 {n_req} 样本, 收到 {len(iq)}, 耗时 {elapsed:.2f}s")
if elapsed > 0:
    print(f"实际采样率 = {len(iq)/elapsed/1e3:.1f} kSPS")
    ok = abs(len(iq)/elapsed - 250000)/250000 < 0.05
    print("RESULT:", "OK" if ok else f"FAIL (实际 {len(iq)/elapsed/1e3:.0f} kHz)")
else:
    print("RESULT: FAIL (耗时 0)")
