# -*- coding: utf-8 -*-
"""修复帧切分 bug: 监测窗口在 6.9s 数据内滑动, 参考固定前2s"""
import io

path = r"C:\Users\iveco\.openclaw\workspace\passive_radar\pr_rsp1_parallel.py"
s = io.open(path, encoding="utf-8").read()

old = '''    # 子帧切分: 每帧用完整参考(2s) + 监测滑动窗口(2s), 保证分辨率
    frame_slices = []
    if N_FRAMES <= 1:
        frame_slices = [(0, min(ns_full, n_ref))]
    else:
        frame_len = min(n_surv, n_ref)  # 2s 窗口
        avail = min(ns_full, n_ref)     # 可用监测长度
        if avail >= frame_len * N_FRAMES:
            hop = (avail - frame_len) // (N_FRAMES - 1)
        else:
            hop = frame_len // 2        # 数据不够则重叠一半
        for k in range(N_FRAMES):
            st = min(k * hop, avail - frame_len)
            frame_slices.append((st, st + frame_len))'''

new = '''    # 子帧切分: 监测窗口在 ns_full 内滑动, 参考固定用前 2s
    frame_slices = []
    if N_FRAMES <= 1:
        frame_slices = [(0, min(ns_full, n_ref))]
    else:
        frame_len = n_surv               # 2s 监测窗口
        avail = ns_full                  # 监测数据全长 (6.9s)
        if avail >= frame_len * N_FRAMES:
            hop = (avail - frame_len) // (N_FRAMES - 1)
        else:
            hop = frame_len // 2
        for k in range(N_FRAMES):
            st = min(k * hop, avail - frame_len)
            frame_slices.append((st, st + frame_len))'''

assert old in s, "frame block not found"
s = s.replace(old, new, 1)

io.open(path, "w", encoding="utf-8").write(s)
print("frame slice bug fixed")
