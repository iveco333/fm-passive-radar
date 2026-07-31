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
DURATION = 3

REF_TIME = 2.0
SURV_TIME = 2.0
MAX_DELAY = 800
DOPPLER_RANGE = 150
DOPPLER_BINS = 61
M = 128
MU = 0.002

MATCH_RANGE_TOL = 5.0
MATCH_DOPPLER_TOL = 40
MIN_SNR = -6

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
    return data_file

# ---- Step 3: 处理 (并行CAF) ----

def step3_process(data_file, adsb_local, adsb_time):
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

    # 3. LMS
    n_ref = int(REF_TIME * FS)
    n_surv = int(SURV_TIME * FS)
    ref = iq[:n_ref]
    surv = iq[int(0.1*FS):int(0.1*FS)+n_surv]
    log(f"[3/6] LMS DPI抑制 ({M} taps)...")
    ns = len(surv)
    rp = np.tile(ref, (ns // len(ref)) + 2)[:ns + M]
    w = np.zeros(M, dtype=np.complex64)
    out = surv.copy().astype(np.complex64)
    B = 4096
    for i in range(0, ns, B):
        chunk = min(B, ns - i)
        for j in range(chunk):
            x = rp[i+j:i+j+M]
            e = out[i+j] - np.dot(w, x)
            w += MU * e * np.conj(x)
            out[i+j] = e
        if (i // B) % 16 == 0:
            print(f'  LMS: {i+chunk}/{ns} ({(i+chunk)*100/ns:.0f}%)')
    log(f"  残差: {np.mean(np.abs(out)):.4f}")
    out = out / (np.sqrt(np.mean(np.abs(out)**2)) + 1e-10)

    # 4. CAF - 多进程并行
    log(f"[4/6] CAF (多进程并行)...")
    n = min(len(ref), len(out))
    ref_c = ref[:n].astype(np.complex64)
    surv_out = out[:n].astype(np.complex64)

    dp = np.linspace(-DOPPLER_RANGE, DOPPLER_RANGE, DOPPLER_BINS)
    ff = 1
    while ff < n + MAX_DELAY:
        ff <<= 1

    r = _caf_multiprocess(ref_c, surv_out, dp, ff, MAX_DELAY, FS, n_workers=4)

    rk = np.arange(MAX_DELAY) * (3e8/FS) / 1000
    rd = 20 * np.log10(np.maximum(r, 1e-10))
    rd -= rd.max()

    # 5. 峰值检测
    c = len(dp) // 2
    mk = np.ones_like(rd, dtype=bool)
    mk[c-1:c+2, :] = False
    rd_masked = rd[mk]
    log(f"  CAF: max={rd_masked.max():.1f}dB, median={np.median(rd_masked):.1f}dB")
    log(f"  阈值: MIN_SNR={MIN_SNR}dB | 匹配距离{MATCH_RANGE_TOL}km | 匹配多普勒{MATCH_DOPPLER_TOL}Hz")

    peaks = []
    fl = rd_masked
    ix = np.argsort(fl, axis=None)[-50:][::-1]
    for idx in ix:
        di = np.where(mk)[0][idx]
        ri = np.where(mk)[1][idx]
        if rd[di, ri] > MIN_SNR:
            peaks.append({'range_km': rk[ri], 'doppler_hz': dp[di], 'snr_db': rd[di, ri]})
    log(f"[5/6] 峰值: {len(peaks)} 个")

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
    data_file = step2_rsp1()
    if data_file is None:
        return
    matches, report_file, sample_time, ps = step3_process(data_file, adsb_local, adsb_time)
    print("\n" + "=" * 60)
    print(f"  匹配: {len(matches)} 个")
    for m in matches:
        print(f"    {m['flight']}: 频差{m['doppler_diff']:.0f}Hz  距离差{m['range_diff']:.1f}km")
    print(f"  报告: {os.path.abspath(report_file)}")
    print("=" * 60)

if __name__ == '__main__':
    main()
