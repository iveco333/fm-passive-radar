# -*- coding: utf-8 -*-
"""在 pr_rsp1_parallel.py 中插入 detect_peaks 函数 + 多帧处理"""
import io, re

path = r"C:\Users\iveco\.openclaw\workspace\passive_radar\pr_rsp1_parallel.py"
s = io.open(path, encoding="utf-8").read()

# 1. 插入 detect_peaks 函数 (在 "# ---- Step 1: ADS-B ----" 之前)
anchor = "\n# ---- Step 1: ADS-B ----"
func = '''
# ---- 峰值检测 (自适应阈值 + 局部峰确认) ----

def detect_peaks(rd, dp, rk):
    """从 CAF 幅度图检测候选峰。返回 [(range_km, doppler_hz, snr_db)]"""
    c = len(dp) // 2
    mk = np.ones_like(rd, dtype=bool)
    mk[c-1:c+2, :] = False  # 屏蔽直达波中心
    rd_masked = rd[mk]

    noise_med = np.median(rd_masked)
    thr_adaptive = noise_med + SNR_OVER_MEDIAN
    log(f"    CAF: max={rd_masked.max():.1f}dB med={noise_med:.1f}dB 阈值={thr_adaptive:.1f}dB")

    cand = np.zeros_like(rd, dtype=bool)
    for di in range(1, rd.shape[0]-1):
        for ri in range(1, rd.shape[1]-1):
            if not mk[di, ri]:
                continue
            v = rd[di, ri]
            if v < thr_adaptive:
                continue
            nb = rd[di-1:di+2, ri-1:ri+2]
            if v >= nb.max() and v >= nb.mean() + PEAK_PROMINENCE:
                cand[di, ri] = True

    peaks = []
    cand_idx = np.argwhere(cand)
    if len(cand_idx) > 0:
        snrs = rd[cand_idx[:,0], cand_idx[:,1]]
        order = np.argsort(snrs)[::-1][:N_PEAKS_MAX]
        for k in order:
            di, ri = cand_idx[k]
            peaks.append({'range_km': float(rk[ri]), 'doppler_hz': float(dp[di]), 'snr_db': float(rd[di, ri])})
    return peaks

'''
assert anchor in s, "anchor1 not found"
s = s.replace(anchor, func + anchor, 1)

io.open(path, "w", encoding="utf-8").write(s)
print("inserted detect_peaks OK")
