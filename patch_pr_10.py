# -*- coding: utf-8 -*-
"""增强峰形检验: 真目标峰尖锐(邻域平坦), 杂波展宽(邻域也高)"""
import io

path = r"C:\Users\iveco\.openclaw\workspace\passive_radar\pr_rsp1_parallel.py"
s = io.open(path, encoding="utf-8").read()

# 降低阈值余量 (6dB), 让真目标进来
old = "SNR_OVER_MEDIAN = 9.0   # 峰必须比噪声中位数高 (dB): 9-10 较严, 6 较松"
new = "SNR_OVER_MEDIAN = 5.0   # 峰必须比噪声中位数高 (dB): 降低让真目标进来, 靠峰形检验滤杂波"
assert old in s
s = s.replace(old, new, 1)

# 增强 detect_peaks: 峰尖度检验 (邻域平均不能接近峰)
old2 = '''    cand = np.zeros_like(rd, dtype=bool)
    for di in range(1, rd.shape[0]-1):
        for ri in range(1, rd.shape[1]-1):
            if not mk[di, ri]:
                continue
            v = rd[di, ri]
            if v < thr_adaptive:
                continue
            nb = rd[di-1:di+2, ri-1:ri+2]
            if v >= nb.max() and v >= nb.mean() + PEAK_PROMINENCE:
                cand[di, ri] = True'''

new2 = '''    cand = np.zeros_like(rd, dtype=bool)
    for di in range(1, rd.shape[0]-1):
        for ri in range(1, rd.shape[1]-1):
            if not mk[di, ri]:
                continue
            v = rd[di, ri]
            if v < thr_adaptive:
                continue
            nb = rd[di-1:di+2, ri-1:ri+2]
            # 峰形检验: 峰 > 邻域最大(不含自身), 且峰 > 邻域平均 + 余量
            # 真目标: 单 cell 尖峰, 邻域接近噪声 -> mean 低
            # 杂波: 展宽, 邻域也高 -> mean 接近峰
            if v > nb.max() and v > nb.mean() + PEAK_PROMINENCE:
                # 额外: 峰比邻域中位数高 (中位数不受其他高cell影响)
                if v > np.median(nb) + PEAK_PROMINENCE + 2.0:
                    cand[di, ri] = True'''

assert old2 in s, "peak check block not found"
s = s.replace(old2, new2, 1)

io.open(path, "w", encoding="utf-8").write(s)
print("peak shape test enhanced")
