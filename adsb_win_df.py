#!/usr/bin/env python3
"""分析 112 位帧的 DF 字段分布 - 判断信号有效性"""
import sys, os
import numpy as np
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

FS = 2.4e6
iq = np.fromfile(os.path.join(os.path.dirname(os.path.abspath(__file__)), "adsb_lo_shift.bin"), dtype=np.complex64)
mag = np.abs(iq)
p99 = np.percentile(mag, 99)
thr = p99 * 0.8
bit = int(FS * 1e-6)
n = len(mag)
above = mag > thr

# 收集所有候选 112 位帧的 bits
all_frames = []
for i in range(200, n - 300):
    if not above[i]:
        continue
    try:
        if above[i+bit] and above[i+2*bit] and above[i+int(3.5*bit)]:
            if not above[i+bit//2] and not above[i+bit+bit//2]:
                bits = []
                ok = True
                for b in range(112):
                    s = i + 8 * bit + b * bit
                    if s + bit >= n:
                        ok = False
                        break
                    win = mag[s:s + bit]
                    bits.append(1 if np.mean(win) > thr else 0)
                if ok:
                    all_frames.append("".join(str(b) for b in bits))
    except IndexError:
        continue

print(f"候选帧: {len(all_frames)}")

# DF = 前 5 bit
from collections import Counter
dfs = Counter()
for f in all_frames:
    df = int(f[:5], 2)
    dfs[df] += 1

print("\nDF 字段分布 (Mode S 帧类型, 合法值: 0-31):")
for df, cnt in sorted(dfs.items()):
    mark = " <-- 合法" if df in (4, 5, 11, 17, 18, 20, 21) else ""
    print(f"  DF={df:2d}: {cnt}{mark}")

# 看几条原始帧
print("\n前 3 条候选帧:")
for f in all_frames[:3]:
    print(" ", f[:20], "...")

# CRC 校验: pyModeS 的 crc 函数
import pyModeS as pms
valid = 0
for f in all_frames:
    try:
        if pms.crc(f) == 0:
            valid += 1
    except Exception:
        pass
print(f"\nCRC 通过: {valid}/{len(all_frames)}")
