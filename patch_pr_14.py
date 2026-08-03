# -*- coding: utf-8 -*-
"""多普勒容差 40 -> 60Hz (飞机机动导致预测偏差, 距离匹配已证明准确)"""
import io

path = r"C:\Users\iveco\.openclaw\workspace\passive_radar\pr_rsp1_parallel_multi.py"
s = io.open(path, encoding="utf-8").read()

old = "MATCH_DOPPLER_TOL = 40"
new = "MATCH_DOPPLER_TOL = 60   # 飞机机动导致多普勒预测偏差, 放宽到60Hz"
assert old in s
s = s.replace(old, new, 1)

io.open(path, "w", encoding="utf-8").write(s)
print("doppler tol 40->60")
