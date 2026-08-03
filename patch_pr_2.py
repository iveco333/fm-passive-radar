# -*- coding: utf-8 -*-
"""替换 step3 的 CAF+峰值检测为多帧版本"""
import io

path = r"C:\Users\iveco\.openclaw\workspace\passive_radar\pr_rsp1_parallel.py"
s = io.open(path, encoding="utf-8").read()

old_start = "# 4. CAF - 多进程并行"
old_end = 'log(f"[5/6] 峰值: {len(peaks)} 个 (候选{int(cand.sum())})")'

i0 = s.find(old_start)
i1 = s.find(old_end)
assert i0 >= 0 and i1 >= 0, f"anchors: {i0} {i1}"
i1 += len(old_end)

new_block = '''# 4. CAF - 多进程并行 (多帧确认: 切 3 个子帧分别算, 峰值求交集)
    log(f"[4/6] CAF (多帧 x{N_FRAMES}, 多进程)...")
    n_full = min(len(ref), len(out))
    ref_c0 = ref[:n_full].astype(np.complex64)
    surv_out0 = out[:n_full].astype(np.complex64)

    dp = np.linspace(-DOPPLER_RANGE, DOPPLER_RANGE, DOPPLER_BINS)
    rk = np.arange(MAX_DELAY) * (3e8/FS) / 1000

    # 子帧长度: 总长 / N_FRAMES (重叠 50%)
    if N_FRAMES <= 1:
        frame_slices = [(0, n_full)]
    else:
        frame_len = n_full // N_FRAMES
        hop = (n_full - frame_len) // (N_FRAMES - 1) if N_FRAMES > 1 else frame_len
        frame_slices = []
        for k in range(N_FRAMES):
            st = min(k * hop, n_full - frame_len)
            frame_slices.append((st, st + frame_len))

    frame_peaks = []
    for fi, (st, en) in enumerate(frame_slices):
        log(f"  帧 {fi+1}/{len(frame_slices)}: [{st}-{en}] ({ (en-st)/FS:.2f}s)")
        ref_f = ref_c0[st:en]
        surv_f = surv_out0[st:en]
        n = len(ref_f)
        ff = 1
        while ff < n + MAX_DELAY:
            ff <<= 1
        r = _caf_multiprocess(ref_f, surv_f, dp, ff, MAX_DELAY, FS, n_workers=4)
        rd = 20 * np.log10(np.maximum(r, 1e-10))
        rd -= rd.max()
        fp = detect_peaks(rd, dp, rk)
        log(f"  帧 {fi+1} 峰值: {len(fp)} 个")
        frame_peaks.append(fp)

    # 多帧交集: 只保留在多数帧中出现的 (range, doppler) 组合
    from collections import defaultdict
    vote = defaultdict(int)
    peak_map = {}
    for fp in frame_peaks:
        for p in fp:
            key = (round(p['range_km'], 1), round(p['doppler_hz'], 0))
            vote[key] += 1
            peak_map[key] = p
    need = max(2, N_FRAMES - 1) if N_FRAMES > 2 else 2  # 3帧中至少2帧出现
    if N_FRAMES <= 1:
        need = 1
    peaks = [peak_map[k] for k, v in vote.items() if v >= need]
    peaks.sort(key=lambda p: -p['snr_db'])
    peaks = peaks[:N_PEAKS_MAX]
    log(f"[5/6] 峰值(多帧确认): {len(peaks)} 个 (候选 {len(vote)} 个唯一位置)")'''

s = s[:i0] + new_block + s[i1:]

io.open(path, "w", encoding="utf-8").write(s)
print("patched multi-frame OK")
