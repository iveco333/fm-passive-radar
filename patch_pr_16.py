# -*- coding: utf-8 -*-
"""加距离上限过滤: 只保留 60km 内的峰, 砍掉远距离杂波"""
import io

path = r"C:\Users\iveco\.openclaw\workspace\passive_radar\pr_rsp1_parallel_multi.py"
s = io.open(path, encoding="utf-8").read()

# 1. 加配置
old = "MATCH_DOPPLER_TOL = 60   # 飞机机动导致多普勒预测偏差, 放宽到60Hz"
new = "MATCH_DOPPLER_TOL = 60   # 飞机机动导致多普勒预测偏差, 放宽到60Hz\nMAX_RANGE_KM = 60      # 只保留 60km 内的峰 (FM被动雷达有效距离, 砍远距杂波)"
assert old in s
s = s.replace(old, new, 1)

# 2. detect_peaks 里加距离过滤
old2 = '''    peaks = []
    cand_idx = np.argwhere(cand)
    if len(cand_idx) > 0:
        snrs = rd[cand_idx[:,0], cand_idx[:,1]]
        order = np.argsort(snrs)[::-1][:N_PEAKS_MAX]
        for k in order:
            di, ri = cand_idx[k]
            peaks.append({'range_km': float(rk[ri]), 'doppler_hz': float(dp[di]), 'snr_db': float(rd[di, ri])})
    return peaks'''
new2 = '''    peaks = []
    cand_idx = np.argwhere(cand)
    if len(cand_idx) > 0:
        snrs = rd[cand_idx[:,0], cand_idx[:,1]]
        order = np.argsort(snrs)[::-1][:N_PEAKS_MAX]
        for k in order:
            di, ri = cand_idx[k]
            r_km = float(rk[ri])
            if r_km > MAX_RANGE_KM:   # 距离上限过滤
                continue
            peaks.append({'range_km': r_km, 'doppler_hz': float(dp[di]), 'snr_db': float(rd[di, ri])})
    return peaks'''
assert old2 in s, "detect_peaks return block not found"
s = s.replace(old2, new2, 1)

io.open(path, "w", encoding="utf-8").write(s)
print("MAX_RANGE_KM filter added")
