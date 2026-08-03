#!/usr/bin/env python3
"""隔离测试: 哪个改动导致 Init 挂掉?
A: 新结构体 + 不写 fsFreq (默认)   → 验证结构体本身是否破坏 API
B: 写 fsFreq 但不设 syncUpdate/reCal
C: 写 fsFreq + syncUpdate=1 (reCal=0)
"""
import sys, os
import numpy as np
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from sdrplay_api import SDRplayAPI

def try_case(label, mode):
    print(f"\n=== {label} ===", flush=True)
    sdr = SDRplayAPI()
    sdr.select_device(0)
    sdr.set_frequency(88e6)
    sdr.set_gain(40)
    # 直接改 bwType (不通过 set_sample_rate, 避免它写 fsFreq)
    from sdrplay_api import BW_1_536
    sdr.ch.tunerParams.bwType = BW_1_536
    if mode == "no_fs":
        print("  (不写 fsFreq, 保持 API 默认)", flush=True)
    elif mode == "fs_only":
        dp = sdr.params.devParams.contents
        print(f"  devParams 指针: {sdr.params.devParams}", flush=True)
        print(f"  默认 fsHz = {dp.fsFreq.fsHz:.1f}", flush=True)
        dp.fsFreq.fsHz = 2.0e6
        print(f"  设置 fsHz = {dp.fsFreq.fsHz/1e6:.1f}M (不设标志)", flush=True)
    elif mode == "fs_sync":
        dp = sdr.params.devParams.contents
        dp.fsFreq.fsHz = 2.0e6
        dp.fsFreq.syncUpdate = 1
        print(f"  设置 fsHz = 2.0M + syncUpdate=1", flush=True)
    try:
        iq = sdr.capture(0.5)
        print(f"  成功! 采到 {len(iq)} 样本", flush=True)
    except Exception as e:
        print(f"  失败: {e}", flush=True)
    try:
        sdr.close()
    except Exception:
        pass

if __name__ == "__main__":
    try_case("A: 结构体+不写fsFreq", "no_fs")
    try_case("B: 写fsHz不设标志", "fs_only")
    try_case("C: 写fsHz+syncUpdate", "fs_sync")
