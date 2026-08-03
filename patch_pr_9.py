# -*- coding: utf-8 -*-
"""修复: 屏蔽区收窄, 只屏蔽 0Hz 直达波中心 1 个 bin"""
import io

path = r"C:\Users\iveco\.openclaw\workspace\passive_radar\pr_rsp1_parallel.py"
s = io.open(path, encoding="utf-8").read()

# detect_peaks 里的屏蔽
old = '''    c = len(dp) // 2
    mk = np.ones_like(rd, dtype=bool)
    mk[c-1:c+2, :] = False  # 屏蔽直达波中心
    rd_masked = rd[mk]'''
new = '''    c = len(dp) // 2
    mk = np.ones_like(rd, dtype=bool)
    # 只屏蔽 0Hz 正中心 1 个 bin (低空近距目标多普勒接近 0, 不能误杀)
    mk[c, :] = False
    rd_masked = rd[mk]'''
assert old in s, "detect_peaks mask not found"
s = s.replace(old, new, 1)

io.open(path, "w", encoding="utf-8").write(s)
print("mask narrowed to center bin only")
