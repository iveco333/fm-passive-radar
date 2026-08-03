# -*- coding: utf-8 -*-
"""修复: 1) 每帧独立参考(同时刻直达波) 2) 投票容差放宽"""
import io

path = r"C:\Users\iveco\.openclaw\workspace\passive_radar\pr_rsp1_parallel.py"
s = io.open(path, encoding="utf-8").read()

# 1. 修帧循环: 每帧 ref 用该帧监测窗口的直达波 (窗口起点 -0.1s, 与 surv 重叠)
old = '''    frame_peaks = []
    for fi, (st, en) in enumerate(frame_slices):
        log(f"  帧 {fi+1}/{len(frame_slices)}: 监测[{st}:{en}] ({ (en-st)/FS:.2f}s)")
        ref = ref_full[:frame_len].astype(np.complex64) if N_FRAMES > 1 else ref_full[:en-st].astype(np.complex64)
        surv = surv_full[st:en].astype(np.complex64)'''

new = '''    frame_peaks = []
    for fi, (st, en) in enumerate(frame_slices):
        log(f"  帧 {fi+1}/{len(frame_slices)}: 监测[{st}:{en}] ({ (en-st)/FS:.2f}s)")
        # 参考 = 该帧监测窗口起点的直达波 (前移 0.1s, 与原设计一致)
        ref_st = max(0, st - int(0.1 * FS))
        ref = iq[ref_st:ref_st + frame_len].astype(np.complex64)
        surv = surv_full[st:en].astype(np.complex64)'''

assert old in s, "frame loop not found"
s = s.replace(old, new, 1)

# 2. 投票容差: range 按 0.5km 聚合, doppler 按 10Hz 聚合 (目标帧间会移动)
old2 = '''    # 多帧交集投票
    from collections import defaultdict
    vote = defaultdict(int)
    peak_map = {}
    for fp in frame_peaks:
        for p in fp:
            key = (round(p['range_km'], 1), round(p['doppler_hz'], 0))
            vote[key] += 1
            peak_map[key] = p
    need = 2 if N_FRAMES > 2 else 1
    peaks = [peak_map[k] for k, v in vote.items() if v >= need]
    peaks.sort(key=lambda p: -p['snr_db'])
    peaks = peaks[:N_PEAKS_MAX]
    log(f"[5/6] 峰值(多帧确认, ≥{need}帧): {len(peaks)} 个 (唯一位置 {len(vote)})")'''

new2 = '''    # 多帧交集投票 (带容差: 距离±0.5km, 多普勒±10Hz)
    from collections import defaultdict
    R_BIN = 0.5   # km
    D_BIN = 10.0  # Hz
    vote = defaultdict(int)
    peak_map = {}
    for fp in frame_peaks:
        for p in fp:
            key = (round(p['range_km'] / R_BIN), round(p['doppler_hz'] / D_BIN))
            vote[key] += 1
            # 保留 SNR 最高的那个
            if key not in peak_map or p['snr_db'] > peak_map[key]['snr_db']:
                peak_map[key] = p
    need = 2 if N_FRAMES > 2 else 1
    peaks = [peak_map[k] for k, v in vote.items() if v >= need]
    peaks.sort(key=lambda p: -p['snr_db'])
    peaks = peaks[:N_PEAKS_MAX]
    log(f"[5/6] 峰值(多帧确认, ≥{need}帧, 容差{R_BIN}km/{D_BIN}Hz): {len(peaks)} 个 (唯一位置 {len(vote)})")'''

assert old2 in s, "vote block not found"
s = s.replace(old2, new2, 1)

io.open(path, "w", encoding="utf-8").write(s)
print("patched: per-frame ref + tolerant voting")
