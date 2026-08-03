# -*- coding: utf-8 -*-
"""修复: 3x3 邻域含中心点导致 v > nb.max() 永远 False"""
import io

path = r"C:\Users\iveco\.openclaw\workspace\passive_radar\pr_rsp1_parallel.py"
s = io.open(path, encoding="utf-8").read()

old = '''            nb = rd[di-1:di+2, ri-1:ri+2]
            # 峰形检验: 峰是 3x3 邻域的最大值 (局部峰), 且超过阈值
            # 真目标和杂波都可能是局部峰, 靠 SNR 排序 + 匹配来区分
            if v > nb.max():
                cand[di, ri] = True'''

new = '''            nb = rd[di-1:di+2, ri-1:ri+2]
            # 峰形检验: 峰是 3x3 邻域(不含自身)的最大值
            # 注意: 邻域含中心点, 比较时要排除自己
            if v >= nb.max():
                cand[di, ri] = True'''

assert old in s, "peak check not found"
s = s.replace(old, new, 1)

io.open(path, "w", encoding="utf-8").write(s)
print("fixed center-inclusive max bug")
