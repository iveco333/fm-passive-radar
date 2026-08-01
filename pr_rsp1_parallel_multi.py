#!/usr/bin/env python3
"""
FM被动雷达 — RSP1 + Pi ADS-B (多核并行版)

和pr_rsp1.py功能一样，但CAF用多进程并行 + 单个S提前算好加速。
"""
import os, sys, time, subprocess, datetime, json, math
import numpy as np
from scipy.fft import fft, ifft
from scipy import signal as sp_signal
from concurrent.futures import ProcessPoolExecutor, as_completed

# ---- CAF多进程Worker（顶层函数，必须可pickle） ----
def _caf_worker_chunk(fd_chunk, ref, S, ff, max_delay, fs):
    """处理一批多普勒通道（直接传数组）"""
    n = ref.shape[0]
    t = np.arange(n, dtype=np.float32)
    result = np.zeros((len(fd_chunk), max_delay), dtype=np.float32)
    for ci, fd in enumerate(fd_chunk):
        sf = ref * np.exp(-2j * np.pi * fd * t / fs)
        R = fft(sf, ff)
        result[ci] = np.abs(ifft(S * np.conj(R))[:max_delay])
    return result

# ========== 配置 ==========
PI = "iveco@172.20.10.8"
FREQ = 87.5e6
FS = 2.0e6
RSP1_GRDB = 20
DURATION = 4            # 单帧: 采集4s (2s参考 + 2s监测)

REF_TIME = 2.0
SURV_TIME = 2.0
MAX_DELAY = 800
DOPPLER_RANGE = 150
DOPPLER_BINS = 61
M = 128
MU = 0.002

MATCH_RANGE_TOL = 5.0
MATCH_DOPPLER_TOL = 60   # 飞机机动导致多普勒预测偏差, 放宽到60Hz
MAX_RANGE_KM = 60      # 只保留 60km 内的峰 (FM被动雷达有效距离, 砍远距杂波)
MIN_SNR = -6

# ---- 假警抑制参数 ----
SNR_OVER_MEDIAN = 5.0   # 峰必须比噪声中位数高 (dB): 降低让真目标进来, 靠峰形检验滤杂波
PEAK_PROMINENCE = 3.0   # 峰必须比周围 3x3 邻域高 (dB)
N_PEAKS_MAX = 15        # 最多保留候选峰数
N_FRAMES = 1            # 单帧模式: 多帧在单通道FM下后段质量差, 用强阈值替代

RX_POS = (34.25, 108.94)
TX_POS = (34.201, 108.954)
RX_ALT = 0
TX_ALT = 0

# 向量化CAF批次大小（每批处理的多普勒通道数）
CAF_BATCH = 5

# ---- Tools ----

def log(msg):
    print(f"[{time.strftime('%H:%M:%S')}] {msg}")

def run(cmd, timeout=120):
    print(f"  $ {cmd}")
    proc = subprocess.Popen(cmd, shell=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                            text=True, encoding='utf-8', errors='replace', bufsize=1)
    try:
        for line in iter(proc.stdout.readline, ''):
            if line:
                print(line.rstrip())
    except KeyboardInterrupt:
        proc.terminate()
        raise
    proc.wait(timeout=timeout)
    return proc.returncode == 0

def haversine(l1, o1, l2, o2):
    R = 6371
    a = math.sin(math.radians(l2 - l1) / 2) ** 2 + \
        math.cos(math.radians(l1)) * math.cos(math.radians(l2)) * \
        math.sin(math.radians(o2 - o1) / 2) ** 2
    return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))

def bearing(lat1, lon1, lat2, lon2):
    dlon = math.radians(lon2 - lon1)
    lat1, lat2 = math.radians(lat1), math.radians(lat2)
    x = math.sin(dlon) * math.cos(lat2)
    y = math.cos(lat1) * math.sin(lat2) - math.sin(lat1) * math.cos(lat2) * math.cos(dlon)
    return (math.degrees(math.atan2(x, y)) + 360) % 360

# ---- CAF多进程并行 ----

def _caf_multiprocess(ref, surv, dp, ff, max_delay, fs, n_workers=4):
    """多进程并行CAF：S提前算好，分到n_workers个进程"""
    nd = len(dp)
    r = np.zeros((nd, max_delay), dtype=np.float32)

    # S所有通道共享，只算一次
    S = fft(surv, ff)

    # 把多普勒通道分成n_workers块
    chunks = []
    chunk_size = max(1, nd // n_workers)
    for i in range(0, nd, chunk_size):
        chunks.append(dp[i:i+chunk_size])

    log(f"  启动 {len(chunks)} 个worker处理 {nd} 个多普勒通道...")
    t0 = time.time()

    with ProcessPoolExecutor(max_workers=n_workers) as executor:
        fut_to_idx = {}
        for ci, chunk in enumerate(chunks):
            fut = executor.submit(_caf_worker_chunk, chunk, ref, S, ff, max_delay, fs)
            fut_to_idx[fut] = ci

        for fut in as_completed(fut_to_idx):
            ci = fut_to_idx[fut]
            try:
                result = fut.result()
                start = sum(len(c) for c in chunks[:ci])
                end = start + len(chunks[ci])
                r[start:end] = result
                elapsed = time.time() - t0
                log(f"  Worker {ci+1}/{len(chunks)} done ({elapsed:.1f}s)")
            except Exception as e:
                log(f"  Worker {ci+1} failed: {e}")

    t_total = time.time() - t0
    log(f"  CAF完成 ({t_total:.1f}s, {nd} bins, {n_workers}进程)")
    return r

# ---- 峰值检测 (自适应阈值 + 局部峰确认) ----

def detect_peaks(rd, dp, rk):
    """从 CAF 幅度图检测候选峰。返回 [(range_km, doppler_hz, snr_db)]"""
    c = len(dp) // 2
    mk = np.ones_like(rd, dtype=bool)
    # 只屏蔽 0Hz 正中心 1 个 bin (低空近距目标多普勒接近 0, 不能误杀)
    mk[c, :] = False
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
            # 峰形检验: 峰是 3x3 邻域(不含自身)的最大值
            # 注意: 邻域含中心点, 比较时要排除自己
            if v >= nb.max():
                cand[di, ri] = True

    peaks = []
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
    return peaks


# ---- Step 1: ADS-B ----

def step1_adsb():
    log("Step 1: 获取ADS-B快照 (Pi)")
    ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    adsb_local = f"adsb_{ts}.json"
    if not run(f"ssh {PI} \"cp /run/readsb/aircraft.json /tmp/adsb_snapshot.json\""):
        return None
    if not run(f"scp {PI}:/tmp/adsb_snapshot.json ./{adsb_local}"):
        return None
    adsb_time = None
    try:
        with open(adsb_local) as f:
            adsb_data = json.load(f)
            now = adsb_data.get('now')
            if now:
                adsb_time = datetime.datetime.fromtimestamp(now).strftime('%Y-%m-%d %H:%M:%S')
    except:
        pass
    log(f"[ADS-B] 快照: {adsb_local} ({adsb_time or '未知'})")
    return adsb_local, adsb_time

# ---- Step 2: RSP1 ----

def step2_rsp1():
    log("Step 2: RSP1采集FM数据")
    ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    data_file = f"fm_rsp1_{ts}.dat"
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), "passive_radar"))
    from sdrplay_api import SDRplayAPI
    log(f"[RSP1] {FREQ/1e6:.1f}MHz | {FS/1e6:.1f}MSPS | {DURATION}s | gRdB={RSP1_GRDB}")
    t_cap_start = datetime.datetime.now()  # 采集开始时刻
    with SDRplayAPI() as sdr:
        sdr.select_device(0)
        sdr.set_frequency(FREQ)
        sdr.set_sample_rate(FS)
        sdr.set_gain(RSP1_GRDB)
        log("[RSP1] 开始采集...")
        iq = sdr.capture(DURATION)
        log(f"[RSP1] {len(iq)} 样本 ({len(iq)/FS:.1f}s)")
    raw = np.zeros(len(iq) * 2, dtype=np.uint8)
    raw[0::2] = ((iq.real + 1.0) * 127.5).clip(0, 255).astype(np.uint8)
    raw[1::2] = ((iq.imag + 1.0) * 127.5).clip(0, 255).astype(np.uint8)
    raw.tofile(data_file)
    log(f"[RSP1] 保存: {data_file}")
    return data_file, t_cap_start

# ---- Step 3: 处理 (并行CAF) ----

def step3_process(data_file, adsb_local, adsb_time, extrap_sec=0.0):
    log("Step 3: 处理 (并行CAF)")
    process_start = time.strftime('%H:%M:%S')
    ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    sample_time = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')

    # 1. 加载IQ
    log("[1/6] 加载IQ...")
    raw = np.fromfile(data_file, dtype=np.uint8)
    iq = (raw.astype(np.float32) - 127.5) / 127.5
    iq = iq[0::2] + 1j * iq[1::2]
    log(f"  {len(iq)} 样本")

    # 2. 预处理
    log("[2/6] 预处理...")
    def dc_block(x, blk=1024):
        o = x.copy()
        for i in range(0, len(x), blk):
            b = o[i:i+blk]
            o[i:i+blk] = b - np.mean(b)
        return o
    iq = dc_block(iq)
    b19, a19 = sp_signal.iirnotch(19000/(FS/2), 30, FS)
    iq = sp_signal.filtfilt(b19, a19, iq)
    sos = sp_signal.butter(5, 100e3, 'low', fs=FS, output='sos')
    iq = sp_signal.sosfilt(sos, iq)

    # 3. LMS DPI 抑制 (整段) + 多帧 CAF
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

    # 子帧切分: 监测窗口在 ns_full 内滑动, 参考固定用前 2s
    frame_slices = []
    frame_len = n_surv                   # 2s 监测窗口 (单帧也用)
    if N_FRAMES <= 1:
        frame_slices = [(0, min(ns_full, n_ref))]
    else:
        avail = ns_full                  # 监测数据全长 (6.9s)
        if avail >= frame_len * N_FRAMES:
            hop = (avail - frame_len) // (N_FRAMES - 1)
        else:
            hop = frame_len // 2
        for k in range(N_FRAMES):
            st = min(k * hop, avail - frame_len)
            frame_slices.append((st, st + frame_len))

    frame_peaks = []
    for fi, (st, en) in enumerate(frame_slices):
        log(f"  帧 {fi+1}/{len(frame_slices)}: 监测[{st}:{en}] ({ (en-st)/FS:.2f}s)")
        # 参考 = 该帧监测窗口起点的直达波 (前移 0.1s, 与原设计一致)
        ref_st = max(0, st - int(0.1 * FS))
        ref = iq[ref_st:ref_st + frame_len].astype(np.complex64)
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

    # 多帧交集投票 (带容差: 距离±0.5km, 多普勒±10Hz)
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
    log(f"[5/6] 峰值(多帧确认, ≥{need}帧, 容差{R_BIN}km/{D_BIN}Hz): {len(peaks)} 个 (唯一位置 {len(vote)})")

    # 6. 匹配ADS-B
# 6. 匹配ADS-B
    log("[6/6] 匹配ADS-B...")
    with open(adsb_local) as f:
        adsb_data = json.load(f)

    tx_rx = haversine(TX_POS[0], TX_POS[1], RX_POS[0], RX_POS[1])
    lam = 3e8 / FREQ

    aircraft = []
    for a in adsb_data.get('aircraft', []):
        if 'lat' not in a or 'lon' not in a:
            continue
        lat, lon = a['lat'], a['lon']
        gs = a.get('gs', 0)
        track = a.get('track', 0)
        alt_raw = a.get('alt_baro', '?')
        flight = a.get('flight', '?').strip()
        # 位置外推: 按速度/航向移动到 FM 采集时刻
        if extrap_sec > 0 and gs > 0:
            v_mps = gs * 0.514444
            dist_m = v_mps * extrap_sec
            brng = track
            # 经纬度移动 (近似球面)
            dlat = dist_m * math.cos(math.radians(brng)) / 111320.0
            dlon = dist_m * math.sin(math.radians(brng)) / (111320.0 * math.cos(math.radians(lat)) + 1e-9)
            lat += dlat
            lon += dlon
        alt_m = float(alt_raw) * 0.3048 if alt_raw not in ('?', None, 'ground') else 0
        alt_display = alt_raw if alt_raw not in ('?', None) else '?'
        rx_ground = haversine(RX_POS[0], RX_POS[1], lat, lon)
        tx_ground = haversine(TX_POS[0], TX_POS[1], lat, lon)
        rx_slant = math.sqrt(rx_ground**2 + ((alt_m - RX_ALT)/1000)**2)
        tx_slant = math.sqrt(tx_ground**2 + ((alt_m - TX_ALT)/1000)**2)
        bi = tx_slant + rx_slant - tx_rx
        v = gs * 0.514444
        vx = v * math.sin(math.radians(track))
        vy = v * math.cos(math.radians(track))
        brng_tx = bearing(TX_POS[0], TX_POS[1], lat, lon)
        brng_rx = bearing(RX_POS[0], RX_POS[1], lat, lon)
        cos_el_tx = tx_ground / tx_slant if tx_slant > 0 else 1.0
        cos_el_rx = rx_ground / rx_slant if rx_slant > 0 else 1.0
        tx_h = (math.sin(math.radians(brng_tx)) * cos_el_tx,
                math.cos(math.radians(brng_tx)) * cos_el_tx)
        rx_h = (math.sin(math.radians(brng_rx)) * cos_el_rx,
                math.cos(math.radians(brng_rx)) * cos_el_rx)
        fd = -(vx * (tx_h[0] + rx_h[0]) + vy * (tx_h[1] + rx_h[1])) / lam
        brng_fr = bearing(RX_POS[0], RX_POS[1], lat, lon)
        aircraft.append({
            'flight': flight, 'alt': alt_display, 'gs': gs,
            'track': track, 'bi_km': bi, 'fd_hz': fd,
            'rx_dist_km': rx_ground, 'rx_slant_km': rx_slant,
            'rx_bearing': brng_fr
        })
    # ---- 详细输出每架ADS-B ----
    log(f"  ADS-B: {len(aircraft)} 架")
    for ac in aircraft:
        v_kmh = ac['gs'] * 1.852
        dir_map = {0:'N',45:'NE',90:'E',135:'SE',180:'S',225:'SW',270:'W',315:'NW'}
        dir_str = min(dir_map.keys(), key=lambda k: abs(k-ac['rx_bearing']))
        log(f"  [ADS-B] {ac['flight']:>8}: "
            f"{ac['rx_dist_km']:5.1f}km/{ac['rx_bearing']:3.0f}°({dir_map[dir_str]:>2}) "
            f"alt={ac['alt']:>6}ft "
            f"spd={ac['gs']:3.0f}kts({v_kmh:3.0f}km/h) "
            f"hdg={ac['track']:3.0f}° "
            f"bi={ac['bi_km']:5.1f}km "
            f"fd={ac['fd_hz']:+.0f}Hz")

    # ---- 匹配 + 未匹配分析 ----
    matches, seen, unmatched_reasons = [], [], []
    for ac in aircraft:
        # 找到最近的PR峰值
        best_peak = None
        best_r_diff = best_d_diff = 999
        for p in peaks:
            r_diff = abs(p['range_km'] - ac['bi_km'])
            d_diff = abs(p['doppler_hz'] - ac['fd_hz'])
            if r_diff + d_diff/10 < best_r_diff + best_d_diff/10:
                best_peak = p
                best_r_diff = r_diff
                best_d_diff = d_diff

        if best_peak is None:
            unmatched_reasons.append((ac, None, 999, 999, "无PR峰值"))
            continue

        if best_r_diff <= MATCH_RANGE_TOL and best_d_diff <= MATCH_DOPPLER_TOL:
            if ac['flight'] not in seen:
                seen.append(ac['flight'])
                matches.append({
                    'flight': ac['flight'], 'pr_range': best_peak['range_km'],
                    'pr_doppler': best_peak['doppler_hz'], 'pr_snr': best_peak['snr_db'],
                    'adsb_range': ac['bi_km'], 'adsb_doppler': ac['fd_hz'],
                    'range_diff': best_r_diff, 'doppler_diff': best_d_diff,
                    'rx_dist_km': ac['rx_dist_km'], 'rx_slant_km': ac['rx_slant_km'],
                    'rx_bearing': ac['rx_bearing'], 'alt': ac['alt'],
                    'gs': ac['gs'], 'track': ac['track']
                })
        else:
            # 分析未匹配原因
            reasons = []
            if best_r_diff > MATCH_RANGE_TOL:
                reasons.append(f"距离超({best_r_diff:.1f}km>{MATCH_RANGE_TOL}km)")
            if best_d_diff > MATCH_DOPPLER_TOL:
                reasons.append(f"多普勒超({best_d_diff:.0f}Hz>{MATCH_DOPPLER_TOL}Hz)")
            if best_peak['snr_db'] < MIN_SNR:
                reasons.append(f"SNR低({best_peak['snr_db']:.1f}dB<{MIN_SNR}dB)")
            reason_str = ", ".join(reasons) if reasons else "未知"
            unmatched_reasons.append((ac, best_peak, best_r_diff, best_d_diff, reason_str))

    # ---- 输出匹配结果 ----
    if matches:
        log(f"  —— 匹配 {len(matches)} 个 ——")
        for m in matches:
            log(f"  [OK] {m['flight']}: "
                f"PR={m['pr_range']:.1f}km/{m['pr_doppler']:+.0f}Hz({m['pr_snr']:.1f}dB) "
                f"ADS-B={m['adsb_range']:.1f}km/{m['adsb_doppler']:+.0f}Hz "
                f"dist_d={m['range_diff']:.1f}km dop_d={m['doppler_diff']:.0f}Hz "
                f"h_dist={m['rx_dist_km']:.1f}km brg={m['rx_bearing']:.0f}deg "
                f"alt={m['alt']}ft hdg={m['track']:.0f}deg spd={m['gs']:.0f}kts")

    # ---- 输出未匹配分析 ----
    if unmatched_reasons:
        log(f"  —— 未匹配 {len(unmatched_reasons)} 个 ——")
        for ac, best_p, r_diff, d_diff, reason in unmatched_reasons:
            near_str = f"最近PR: {best_p['range_km']:.1f}km/{best_p['doppler_hz']:+.0f}Hz" if best_p else ""
            log(f"  [NO] {ac['flight']}: "
                f"ADS-B bi={ac['bi_km']:.1f}km fd={ac['fd_hz']:+.0f}Hz "
                f"({near_str}) "
                f"reason: {reason}")

    # ---- 假信号统计 ----
    matched_peaks = sum(1 for p in peaks for m in matches if abs(p['range_km']-m['pr_range'])<0.5 and abs(p['doppler_hz']-m['pr_doppler'])<5)
    false_alarms = len(peaks) - matched_peaks
    log(f"  [FA] false alarms: {false_alarms}/{len(peaks)} ({false_alarms*100//len(peaks) if peaks else 0}% unmatched)")

    # 报告
    report_file = f"pr_parallel_{ts}.md"
    tx_rx_dist = haversine(TX_POS[0], TX_POS[1], RX_POS[0], RX_POS[1])
    with open(report_file, 'w') as f:
        f.write("# PR vs ADS-B 对照报告 (并行版)\n\n## 系统参数\n\n")
        f.write(f"| 参数 | 值 |\n|------|-----|\n")
        f.write(f"| 采集 | RSP1 @ {FREQ/1e6:.1f}MHz gRdB={RSP1_GRDB} |\n")
        f.write(f"| 处理 | REF={REF_TIME}s LMS={M} MAX_DELAY={MAX_DELAY} |\n")
        f.write(f"| CAF | ±{DOPPLER_RANGE}Hz/{DOPPLER_BINS}bins S提前算优化 |\n")
        f.write(f"| 发射台 | ({TX_POS[0]:.3f}, {TX_POS[1]:.3f}) |\n")
        f.write(f"| 接收点 | ({RX_POS[0]:.3f}, {RX_POS[1]:.3f}) 基线{tx_rx_dist:.2f}km |\n")
        f.write(f"| 采集时间 | {sample_time} | ADS-B: {adsb_time or '未知'} |\n\n")
        f.write("## PR峰值(Top20)\n\n| 距离(km) | 多普勒(Hz) | SNR(dB) |\n")
        f.write("|---------|-----------|--------|\n")
        for p in peaks[:20]:
            f.write(f"| {p['range_km']:.1f} | {p['doppler_hz']:+.0f} | {p['snr_db']:.1f} |\n")
        f.write("\n## ADS-B\n\n| 航班 | 高度 | 速度 | 航向 | 水平距 | 斜距 | 方位 | 双基地 | 多普勒(3D) |\n")
        f.write("|-----|------|------|------|--------|------|------|-------|----------|\n")
        for ac in sorted(aircraft, key=lambda x: x['bi_km']):
            f.write(f"| {ac['flight']} | {ac['alt']} | {ac['gs']:.0f}kts | {ac['track']:.0f}° | "
                    f"{ac['rx_dist_km']:.1f}km | {ac['rx_slant_km']:.1f}km | {ac['rx_bearing']:.0f}° | "
                    f"{ac['bi_km']:.1f}km | {ac['fd_hz']:.0f}Hz |\n")
        f.write("\n## 匹配\n\n")
        if matches:
            for m in matches:
                f.write(f"- {m['flight']}: PR={m['pr_range']:.1f}km/{m['pr_doppler']:+.0f}Hz "
                        f"ADS-B={m['adsb_range']:.1f}km/{m['adsb_doppler']:+.0f}Hz "
                        f"频差{m['doppler_diff']:.0f}Hz\n")
        else:
            f.write("无匹配\n")

    log(f"报告: {report_file}")

    # 绘图
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    caf_db = np.clip(rd, -25, 0)
    fig, ax = plt.subplots(figsize=(12, 7))
    extent = [rk[0], rk[-1], dp[0], dp[-1]]
    im = ax.imshow(caf_db, aspect='auto', origin='lower', extent=extent,
                   cmap='inferno', vmin=-20, vmax=0)
    if peaks:
        ax.scatter([p['range_km'] for p in peaks], [p['doppler_hz'] for p in peaks],
                   c='lime', s=30, marker='o', edgecolors='black', linewidths=0.5)
    ax.set_xlabel('Range (km)')
    ax.set_ylabel('Doppler (Hz)')
    ax.set_title(f'PR-DDR {FREQ/1e6:.1f}MHz (S precomputed)')
    plt.colorbar(im, ax=ax, label='dB')
    plt.tight_layout()
    plt.savefig(f"pr_parallel_{ts}.png", dpi=150)
    plt.close()
    log(f"图像: pr_parallel_{ts}.png")

    return matches, report_file, sample_time, process_start


def print_config():
    print("=" * 60)
    print("  FM-DDR -- RSP1 + Pi ADS-B (多进程并行)")
    print("=" * 60)
    print(f"  [设备]      RSP1 gRdB={RSP1_GRDB}")
    print(f"  [频率]      {FREQ/1e6:.1f} MHz")
    print(f"  [处理参数]  REF={REF_TIME}s MAX_DELAY={MAX_DELAY} DOPPLER=+/-{DOPPLER_RANGE}Hz/{DOPPLER_BINS}bins")
    print(f"  [CAF]        4进程并行, S提前算")

    print(f"  [阈值]       MIN_SNR={MIN_SNR}dB | 匹配距离<={MATCH_RANGE_TOL}km | 多普勒<={MATCH_DOPPLER_TOL}Hz")
    print(f"  [发射台]    ({TX_POS[0]:.3f}, {TX_POS[1]:.3f})")
    print(f"  [接收点]    ({RX_POS[0]:.3f}, {RX_POS[1]:.3f})")
    print()


def main():
    print_config()
    result = step1_adsb()
    if result is None:
        return
    adsb_local, adsb_time = result
    import datetime as _dt
    t_adsb = _dt.datetime.strptime(adsb_time, '%Y-%m-%d %H:%M:%S') if adsb_time else None
    data_file, t_cap_start = step2_rsp1()
    if data_file is None:
        return
    # 外推目标 = 采集中间时刻 (采集开始 + 时长/2), 比采集完成时刻更准
    t_mid = t_cap_start + _dt.timedelta(seconds=DURATION / 2.0)
    extrap_sec = (t_mid - t_adsb).total_seconds() if t_adsb else 0.0
    log(f"  [时间] ADS-B快照 -> 采集中间 外推 {extrap_sec:.0f}s")
    matches, report_file, sample_time, ps = step3_process(data_file, adsb_local, adsb_time, extrap_sec)
    print("\n" + "=" * 60)
    print(f"  匹配: {len(matches)} 个")
    for m in matches:
        print(f"    {m['flight']}: 频差{m['doppler_diff']:.0f}Hz  距离差{m['range_diff']:.1f}km")
    print(f"  报告: {os.path.abspath(report_file)}")
    print("=" * 60)

if __name__ == '__main__':
    main()
