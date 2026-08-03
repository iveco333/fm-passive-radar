# -*- coding: utf-8 -*-
"""放宽峰形检验: 去掉过严的中位数条件, 保留峰>邻域最大"""
import io

path = r"C:\Users\iveco\.openclaw\workspace\passive_radar\pr_rsp1_parallel.py"
s = io.open(path, encoding="utf-8").read()

old = '''            nb = rd[di-1:di+2, ri-1:ri+2]
            # 峰形检验: 峰 > 邻域最大(不含自身), 且峰 > 邻域平均 + 余量
            # 真目标: 单 cell 尖峰, 邻域接近噪声 -> mean 低
            # 杂波: 展宽, 邻域也高 -> mean 接近峰
            if v > nb.max() and v > nb.mean() + PEAK_PROMINENCE:
                # 额外: 峰比邻域中位数高 (中位数不受其他高cell影响)
                if v > np.median(nb) + PEAK_PROMINENCE + 2.0:
                    cand[di, ri] = True'''

new = '''            nb = rd[di-1:di+2, ri-1:ri+2]
            # 峰形检验: 峰是 3x3 邻域的最大值 (局部峰), 且超过阈值
            # 真目标和杂波都可能是局部峰, 靠 SNR 排序 + 匹配来区分
            if v > nb.max():
                cand[di, ri] = True'''

assert old in s, "peak shape block not found"
s = s.replace(old, new, 1)

io.open(path, "w", encoding="utf-8").write(s)
print("peak shape relaxed")
