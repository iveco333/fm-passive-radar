# -*- coding: utf-8 -*-
"""修复 N_FRAMES=1 时 frame_len 未定义"""
import io

path = r"C:\Users\iveco\.openclaw\workspace\passive_radar\pr_rsp1_parallel.py"
s = io.open(path, encoding="utf-8").read()

old = '''    # 子帧切分: 监测窗口在 ns_full 内滑动, 参考固定用前 2s
    frame_slices = []
    if N_FRAMES <= 1:
        frame_slices = [(0, min(ns_full, n_ref))]
    else:
        frame_len = n_surv               # 2s 监测窗口
        avail = ns_full                  # 监测数据全长 (6.9s)'''

new = '''    # 子帧切分: 监测窗口在 ns_full 内滑动, 参考固定用前 2s
    frame_slices = []
    frame_len = n_surv                   # 2s 监测窗口 (单帧也用)
    if N_FRAMES <= 1:
        frame_slices = [(0, min(ns_full, n_ref))]
    else:
        avail = ns_full                  # 监测数据全长 (6.9s)'''

assert old in s, "frame block not found"
s = s.replace(old, new, 1)

io.open(path, "w", encoding="utf-8").write(s)
print("frame_len fix OK")
