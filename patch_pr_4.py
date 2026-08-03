# -*- coding: utf-8 -*-
"""修正帧切分: 每帧 = 完整2s参考 + 2s监测窗口(滑动), 保持分辨率"""
import io

path = r"C:\Users\iveco\.openclaw\workspace\passive_radar\pr_rsp1_parallel.py"
s = io.open(path, encoding="utf-8").read()

old = '''    # 子帧切分: 监测窗口切成 N_FRAMES 段 (每段 SURV_TIME)
    frame_slices = []
    if N_FRAMES <= 1:
        frame_slices = [(0, min(ns_full, n_ref))]
    else:
        avail = min(ns_full, n_ref)  # 参考与监测重叠部分
        frame_len = avail // N_FRAMES
        for k in range(N_FRAMES):
            st = k * frame_len
            frame_slices.append((st, st + frame_len))'''

new = '''    # 子帧切分: 每帧用完整参考(2s) + 监测滑动窗口(2s), 保证分辨率
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

assert old in s, "frame slice block not found"
s = s.replace(old, new, 1)

# 同时修正帧内 LMS: ref 应取完整参考(帧长), 之前写法 ref_full[:en-st] 对 2s 帧正好
old2 = "        ref = ref_full[:en-st].astype(np.complex64)  # 参考取帧长 (或2s)"
new2 = "        ref = ref_full[:frame_len].astype(np.complex64) if N_FRAMES > 1 else ref_full[:en-st].astype(np.complex64)"
assert old2 in s, "ref line not found"
s = s.replace(old2, new2, 1)

io.open(path, "w", encoding="utf-8").write(s)
print("frame slicing fixed OK")
