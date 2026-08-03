# -*- coding: utf-8 -*-
"""回退到高质量单帧 + 强阈值 (多帧在当前硬件下效果差)"""
import io

path = r"C:\Users\iveco\.openclaw\workspace\passive_radar\pr_rsp1_parallel.py"
s = io.open(path, encoding="utf-8").read()

# 1. N_FRAMES -> 1 (单帧), DURATION 回到 3s (省时间)
old = "N_FRAMES = 3            # 多帧确认帧数 (设为1=关闭, 3=连续3帧都出现才算真目标)"
new = "N_FRAMES = 1            # 单帧模式: 多帧在单通道FM下后段质量差, 用强阈值替代"
assert old in s
s = s.replace(old, new, 1)

old = "DURATION = 7"
new = "DURATION = 4            # 单帧: 采集4s (2s参考 + 2s监测)"
assert old in s
s = s.replace(old, new, 1)

# 2. SNR_OVER_MEDIAN: 6 -> 9 (更强的自适应阈值)
old = "SNR_OVER_MEDIAN = 6.0   # 峰必须比噪声中位数高这么多 (dB) 才算候选"
new = "SNR_OVER_MEDIAN = 9.0   # 峰必须比噪声中位数高 (dB): 9-10 较严, 6 较松"
assert old in s
s = s.replace(old, new, 1)

# 3. N_PEAKS_MAX 25 -> 15
old = "N_PEAKS_MAX = 25        # 最多保留候选峰数"
new = "N_PEAKS_MAX = 15        # 最多保留候选峰数"
assert old in s
s = s.replace(old, new, 1)

io.open(path, "w", encoding="utf-8").write(s)
print("reverted to single-frame + strong threshold")
