# -*- coding: utf-8 -*-
"""修正多帧逻辑: 参考固定2s, 监测窗口滑动, 每帧独立做LMS+CAF"""
import io

path = r"C:\Users\iveco\.openclaw\workspace\passive_radar\pr_rsp1_parallel.py"
s = io.open(path, encoding="utf-8").read()

# 找到 step3 中 LMS + CAF 的完整段落
i_lms = s.find("# 3. LMS")
i_adsb = s.find("# 6. 匹配ADS-B")
assert i_lms >= 0 and i_adsb >= 0, f"{i_lms} {i_adsb}"

old_block = s[i_lms:i_adsb]

new_block = '''# 3. LMS DPI 抑制 (整段) + 多帧 CAF
    log(f"[3/6] LMS DPI抑制 ({M} taps)...")
    n_ref = int(REF_TIME * FS)
    n_surv = int(SURV_TIME * FS)
    ref_full = iq[:n_ref]
    # 监测段: 从 0.1s 起, 尽量长
    surv_full = iq[int(0.1*FS):]
    ns_full = len(surv_full)
    log(f"  参考 {n_ref} samples ({REF_TIME}s), 监测 {ns_full} samples ({ns_full/FS:.1f}s)")

    dp = np.linspace(-DOPPLER_RANGE, DOPPLER_RANGE, DOPPLER_BINS)
    rk = np.arange(MAX_DELAY) * (3e8/FS) / 1000

    # 子帧切分: 监测窗口切成 N_FRAMES 段 (每段 SURV_TIME)
    frame_slices = []
    if N_FRAMES <= 1:
        frame_slices = [(0, min(ns_full, n_ref))]
    else:
        avail = min(ns_full, n_ref)  # 参考与监测重叠部分
        frame_len = avail // N_FRAMES
        for k in range(N_FRAMES):
            st = k * frame_len
            frame_slices.append((st, st + frame_len))

    frame_peaks = []
    for fi, (st, en) in enumerate(frame_slices):
        log(f"  帧 {fi+1}/{len(frame_slices)}: 监测[{st}:{en}] ({ (en-st)/FS:.2f}s)")
        ref = ref_full[:en-st].astype(np.complex64)  # 参考取帧长 (或2s)
        surv = surv_full[st:en].astype(np.complex64)

        # LMS
        ns = len(surv)
        M_local = min(M, ns // 4)
        rp = np.tile(ref, (ns // len(ref)) + 2)[:ns + M_local]
        w = np.zeros(M_local, dtype=np.complex64)
        out = surv.copy()
        B = 4096
        for i in range(0, ns, B):
            chunk = min(B, ns - i)
            for j in range(chunk):
                x = rp[i+j:i+j+M_local]
                e = out[i+j] - np.dot(w, x)
                w += MU * e * np.conj(x)
                out[i+j] = e
        out = out / (np.sqrt(np.mean(np.abs(out)**2)) + 1e-10)

        # CAF
        n = min(len(ref), len(out))
        ref_c = ref[:n].astype(np.complex64)
        surv_out = out[:n].astype(np.complex64)
        ff = 1
        while ff < n + MAX_DELAY:
            ff <<= 1
        r = _caf_multiprocess(ref_c, surv_out, dp, ff, MAX_DELAY, FS, n_workers=4)
        rd = 20 * np.log10(np.maximum(r, 1e-10))
        rd -= rd.max()
        fp = detect_peaks(rd, dp, rk)
        log(f"  帧 {fi+1} 峰值: {len(fp)} 个")
        frame_peaks.append(fp)

    # 多帧交集投票
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
    log(f"[5/6] 峰值(多帧确认, ≥{need}帧): {len(peaks)} 个 (唯一位置 {len(vote)})")

    # 6. 匹配ADS-B
'''
s = s[:i_lms] + new_block + s[i_adsb:]

io.open(path, "w", encoding="utf-8").write(s)
print("patched LMS+CAF multi-frame OK")
