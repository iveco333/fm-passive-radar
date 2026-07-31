#!/usr/bin/env python3
"""
FM被动雷达 — Windows RSP1 + Pi ADS-B 模式

Pi只管ADS-B快照（不碰readsb），Windows RSP1做FM采集 + 处理对比

用法: python pr_rsp1.py
"""
import os, sys, time, subprocess, datetime, json, math
import numpy as np
from scipy.fft import fft, ifft
from scipy import signal as sp_signal

# ========== 配置 ==========
PI = "iveco@172.20.10.8"
FREQ = 87.5e6           # FM 87.5 MHz (扫描最强台 -1.9 dBFS, 对比胜出)
FS = 2.0e6
RSP1_GRDB = 20           # RSP1增益 (gRdB, 20=最大)
DURATION = 3             # 采集时长
NSAMP = int(FS * DURATION)

# 处理参数
REF_TIME = 2.0
SURV_TIME = 2.0
MAX_DELAY = 800
DOPPLER_RANGE = 150
DOPPLER_BINS = 61
M = 128
MU = 0.002

# 匹配阈值
MATCH_RANGE_TOL = 5.0
MATCH_DOPPLER_TOL = 40
MIN_SNR = -6

# 位置 (西安)
RX_POS = (34.25, 108.94)
TX_POS = (34.201, 108.954)
RX_ALT = 0
TX_ALT = 0

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

# ---- Step 1: Pi只取ADS-B ----

def step1_adsb():
    """只从Pi获取ADS-B快照，不碰readsb"""
    log("Step 1: 获取ADS-B快照 (Pi)")
    ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    adsb_local = f"adsb_{ts}.json"

    # 在Pi上复制一份最新快照（系统跑着readsb，数据一直在更新）
    log("[ADS-B 1090MHz] 在Pi上保存飞机快照...")
    if not run(f"ssh {PI} \"cp /run/readsb/aircraft.json /tmp/adsb_snapshot.json\""):
        log("[ADS-B] 快照失败")
        return None

    # scp下载
    log(f"[ADS-B 1090MHz] 下载快照...")
    if not run(f"scp {PI}:/tmp/adsb_snapshot.json ./{adsb_local}"):
        log("[ADS-B] 下载失败")
        return None

    # 解析时间戳
    adsb_time = None
    try:
        with open(adsb_local) as f:
            adsb_data = json.load(f)
            now = adsb_data.get('now')
            if now:
                adsb_time = datetime.datetime.fromtimestamp(now).strftime('%Y-%m-%d %H:%M:%S')
    except:
        pass

    log(f"[ADS-B 1090MHz] 快照已保存: {adsb_local}  (时间: {adsb_time or '未知'})")
    return adsb_local, adsb_time

# ---- Step 2: RSP1采集FM ----

def step2_rsp1():
    """Windows RSP1本地采集FM数据"""
    log("Step 2: RSP1采集FM数据")
    ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    data_file = f"fm_rsp1_{ts}.dat"

    sys.path.insert(0, os.path.join(os.path.dirname(__file__), "passive_radar"))
    from sdrplay_api import SDRplayAPI

    log(f"[RSP1] 频率: {FREQ / 1e6:.1f} MHz | 采样率: {FS / 1e6:.1f} MSPS | 时长: {DURATION}s | gRdB: {RSP1_GRDB}")

    with SDRplayAPI() as sdr:
        sdr.select_device(0)
        sdr.set_frequency(FREQ)
        # RSP1采样率控制: BW_1_536 (1536) → 1.94 MSPS, BW_5_000 (5000) → 6 MSPS
        # 这里用 BW_1_536 最接近2MSPS
        sdr.set_sample_rate(FS)
        sdr.set_gain(RSP1_GRDB)
        log("[RSP1] 开始采集...")
        t0 = time.time()
        iq = sdr.capture(DURATION)
        t1 = time.time()
        log(f"[RSP1] 采集完成: {len(iq)} 样本 ({t1 - t0:.1f}s)")

    # 保存raw
    raw = np.zeros(len(iq) * 2, dtype=np.uint8)
    raw[0::2] = ((iq.real + 1.0) * 127.5).clip(0, 255).astype(np.uint8)
    raw[1::2] = ((iq.imag + 1.0) * 127.5).clip(0, 255).astype(np.uint8)
    raw.tofile(data_file)
    log(f"[RSP1] 原始数据保存: {data_file} ({os.path.getsize(data_file)} bytes)")

    return data_file

# ---- Step 3: 处理（从pr_cross_platform.py移植） ----

def step3_process(data_file, adsb_local, adsb_time):
    """处理FM数据 + ADS-B对比"""
    log("Step 3: 处理 - FM + ADS-B 对比")
    process_start = time.strftime('%H:%M:%S')
    ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")

    sample_time = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')

    log(f"[处理] 数据文件: {data_file}")
    log(f"[处理] ADS-B快照时间: {adsb_time or '未知'}")
    log(f"[处理] 内容: LMS → CAF → 峰值检测 → ADS-B匹配")

    # 1. 加载IQ
    log("[处理1/6] 加载IQ数据...")
    raw = np.fromfile(data_file, dtype=np.uint8)
    iq = (raw.astype(np.float32) - 127.5) / 127.5
    iq = iq[0::2] + 1j * iq[1::2]
    log(f"  {len(iq)} 样本 ({len(iq) / FS:.1f}s)")

    # 2. 预处理
    log("[处理2/6] 预处理...")

    def dc_block(x, blk=1024):
        o = x.copy()
        for i in range(0, len(x), blk):
            b = o[i:i + blk]
            o[i:i + blk] = b - np.mean(b)
        return o

    iq = dc_block(iq)
    b19, a19 = sp_signal.iirnotch(19000 / (FS / 2), 30, FS)
    iq = sp_signal.filtfilt(b19, a19, iq)
    sos = sp_signal.butter(5, 100e3, 'low', fs=FS, output='sos')
    iq = sp_signal.sosfilt(sos, iq)

    # 3. LMS DPI
    n_ref = int(REF_TIME * FS)
    n_surv = int(SURV_TIME * FS)
    ref = iq[:n_ref]
    surv = iq[int(0.1 * FS):int(0.1 * FS) + n_surv]

    log(f"[处理3/6] LMS自适应滤波(DPI抑制, {M} taps)...")
    ns = len(surv)
    rp = np.tile(ref, (ns // len(ref)) + 2)[:ns + M]
    w = np.zeros(M, dtype=np.complex64)
    out = surv.copy().astype(np.complex64)

    B = 4096
    for i in range(0, ns, B):
        chunk = min(B, ns - i)
        for j in range(chunk):
            x = rp[i + j:i + j + M]
            e = out[i + j] - np.dot(w, x)
            w += MU * e * np.conj(x)
            out[i + j] = e
        if (i // B) % 16 == 0:
            print(f'  LMS: {i + chunk}/{ns} ({(i + chunk) * 100 / ns:.0f}%)')

    log(f"  完成. 残差: {np.mean(np.abs(out)):.4f}")
    out = out / (np.sqrt(np.mean(np.abs(out) ** 2)) + 1e-10)

    # 4. CAF
    log("[处理4/6] CAF互模糊函数...")
    n = min(len(ref), len(out))
    ref_c = ref[:n]
    surv_out = out[:n]

    dp = np.linspace(-DOPPLER_RANGE, DOPPLER_RANGE, DOPPLER_BINS)
    ff = 1
    while ff < n + MAX_DELAY:
        ff <<= 1

    r = np.zeros((len(dp), MAX_DELAY), dtype=np.float32)
    t = np.arange(n, dtype=np.float32)

    for di, fd in enumerate(dp):
        if di % 5 == 0:
            log(f"  Doppler {di + 1}/{len(dp)} ({fd:+.0f} Hz)")
        sf = ref_c * np.exp(-2j * np.pi * fd * t / FS)
        S = fft(surv_out, ff)
        R = fft(sf, ff)
        r[di] = np.abs(ifft(S * np.conj(R))[:MAX_DELAY])

    rk = np.arange(MAX_DELAY) * (3e8 / FS) / 1000
    rd = 20 * np.log10(np.maximum(r, 1e-10))
    rd -= rd.max()

    # 5. 峰值检测
    c = len(dp) // 2
    mk = np.ones_like(rd, dtype=bool)
    mk[c - 1:c + 2, :] = False

    # Debug: CAF统计
    rd_masked = rd[mk]
    log(f"  [DEBUG] CAF stats: max={rd_masked.max():.1f}dB, median={np.median(rd_masked):.1f}dB, mean={np.mean(rd_masked):.1f}dB, std={np.std(rd_masked):.1f}dB")
    log(f"  [DEBUG] 零多普勒带(excluded): max={rd[c-1:c+2,:].max():.1f}dB")

    peaks = []
    fl = rd_masked
    ix = np.argsort(fl, axis=None)[-50:][::-1]
    for idx in ix:
        di = np.where(mk)[0][idx]
        ri = np.where(mk)[1][idx]
        if rd[di, ri] > MIN_SNR:
            peaks.append({
                'range_km': rk[ri],
                'doppler_hz': dp[di],
                'snr_db': rd[di, ri]
            })

    log(f"[处理5/6] 峰值检测: {len(peaks)} 个")

    # 6. 加载ADS-B并匹配
    log("[处理5/6] 加载ADS-B数据...")
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

        rx_slant = math.sqrt(rx_ground ** 2 + ((alt_m - RX_ALT) / 1000) ** 2)
        tx_slant = math.sqrt(tx_ground ** 2 + ((alt_m - TX_ALT) / 1000) ** 2)
        bi = tx_slant + rx_slant - tx_rx

        # 3D多普勒
        v = gs * 0.514444
        vx = v * math.sin(math.radians(track))
        vy = v * math.cos(math.radians(track))

        brng_tx_to_tgt = bearing(TX_POS[0], TX_POS[1], lat, lon)
        brng_rx_to_tgt = bearing(RX_POS[0], RX_POS[1], lat, lon)

        cos_el_tx = tx_ground / tx_slant if tx_slant > 0 else 1.0
        cos_el_rx = rx_ground / rx_slant if rx_slant > 0 else 1.0

        tx_h = (math.sin(math.radians(brng_tx_to_tgt)) * cos_el_tx,
                math.cos(math.radians(brng_tx_to_tgt)) * cos_el_tx)
        rx_h = (math.sin(math.radians(brng_rx_to_tgt)) * cos_el_rx,
                math.cos(math.radians(brng_rx_to_tgt)) * cos_el_rx)

        fd = -(vx * (tx_h[0] + rx_h[0]) + vy * (tx_h[1] + rx_h[1])) / lam
        brng_from_rx = bearing(RX_POS[0], RX_POS[1], lat, lon)

        aircraft.append({
            'flight': flight, 'alt': alt_display, 'gs': gs,
            'track': track, 'bi_km': bi, 'fd_hz': fd,
            'rx_dist_km': rx_ground, 'rx_slant_km': rx_slant,
            'rx_bearing': brng_from_rx
        })

    log(f"  ADS-B飞机: {len(aircraft)} 架")

    # 匹配
    log("[处理6/6] 匹配PR峰值与ADS-B...")
    matches, seen = [], set()
    for peak in sorted(peaks, key=lambda p: -p['snr_db']):
        for ac in aircraft:
            r_diff = abs(peak['range_km'] - ac['bi_km'])
            d_diff = abs(peak['doppler_hz'] - ac['fd_hz'])
            if r_diff <= MATCH_RANGE_TOL and d_diff <= MATCH_DOPPLER_TOL and ac['flight'] not in seen:
                seen.add(ac['flight'])
                matches.append({
                    'flight': ac['flight'],
                    'pr_range': peak['range_km'],
                    'pr_doppler': peak['doppler_hz'],
                    'pr_snr': peak['snr_db'],
                    'adsb_range': ac['bi_km'],
                    'adsb_doppler': ac['fd_hz'],
                    'range_diff': r_diff,
                    'doppler_diff': d_diff,
                    'rx_dist_km': ac['rx_dist_km'],
                    'rx_slant_km': ac['rx_slant_km'],
                    'rx_bearing': ac['rx_bearing'],
                    'alt': ac['alt']
                })

    if matches:
        for m in matches:
            log(f"  [匹配] {m['flight']}: PR={m['pr_range']:.1f}km/{m['pr_doppler']:+.0f}Hz(SNR{m['pr_snr']:.1f}dB) "
                f"vs ADS-B={m['adsb_range']:.1f}km/{m['adsb_doppler']:+.0f}Hz "
                f"(频差{m['doppler_diff']:.0f}Hz, 水平{m['rx_dist_km']:.1f}km, 高度{m['alt']}ft, 方位{m['rx_bearing']:.0f}°)")
    else:
        log("  [对比] 无匹配")

    # 报告
    report_file = f"pr_report_rsp1_{ts}.md"
    tx_rx_dist = haversine(TX_POS[0], TX_POS[1], RX_POS[0], RX_POS[1])
    with open(report_file, 'w') as f:
        f.write("# PR vs ADS-B 对照报告 (RSP1)\n\n")
        f.write("---\n\n")
        f.write("### 系统参数\n\n")
        f.write(f"| 参数 | 值 |\n")
        f.write(f"|------|-----|\n")
        f.write(f"| 数据采集设备 | Windows RSP1 (SDRplay RSP1) |\n")
        f.write(f"| FM频率 | {FREQ / 1e6:.1f} MHz |\n")
        f.write(f"| 采样率 | {FS / 1e6:.1f} MSPS |\n")
        f.write(f"| 采集时长 | {DURATION} s |\n")
        f.write(f"| RSP1增益 | gRdB={RSP1_GRDB} |\n")
        f.write(f"| 发射台位置 | ({TX_POS[0]:.3f}, {TX_POS[1]:.3f}) |\n")
        f.write(f"| 接收点位置 | ({RX_POS[0]:.3f}, {RX_POS[1]:.3f}) |\n")
        f.write(f"| 收发基线距 | {tx_rx_dist:.2f} km |\n")
        f.write(f"| MAX_DELAY | {MAX_DELAY} (~{MAX_DELAY * 3e8 / FS / 1000:.0f} km) |\n")
        f.write(f"| 参考时长 | {REF_TIME} s (多普勒分辨率 {1/REF_TIME:.1f} Hz) |\n")
        f.write(f"| 多普勒范围 | ±{DOPPLER_RANGE} Hz / {DOPPLER_BINS} bins |\n")
        f.write(f"| LMS taps | {M} (μ={MU}) |\n")
        f.write(f"| 峰值门限 | {MIN_SNR} dB |\n")
        f.write(f"| 匹配容差 | 距离±{MATCH_RANGE_TOL}km, 多普勒±{MATCH_DOPPLER_TOL}Hz |\n")
        f.write(f"| ADS-B来源 | {PI} (readsb, 不中断服务) |\n")
        f.write(f"| 采集时间 | {sample_time} |\n")
        f.write(f"| ADS-B快照时间 | {adsb_time or '未知'} |\n")
        f.write("\n---\n\n")
        f.write("## PR峰值 (Top 20)\n\n")
        f.write("| 距离(km) | 多普勒(Hz) | SNR(dB) |\n")
        f.write("|---------|-----------|--------|\n")
        for p in peaks[:20]:
            f.write(f"| {p['range_km']:.1f} | {p['doppler_hz']:+.0f} | {p['snr_db']:.1f} |\n")

        f.write("\n## ADS-B 飞机\n\n")
        f.write("| 航班 | 高度(ft) | 速度(kts) | 航向 | 距我(水平) | 距我(斜距) | 方位 | 双基地距离 | 多普勒(3D) |\n")
        f.write("|-----|---------|-----------|------|-----------|----------|------|----------|----------|\n")
        for ac in sorted(aircraft, key=lambda x: x['bi_km']):
            f.write(f"| {ac['flight']} | {ac['alt']} | {ac['gs']:.0f} | {ac['track']:.0f}° | "
                    f"{ac['rx_dist_km']:.1f}km | {ac['rx_slant_km']:.1f}km | {ac['rx_bearing']:.0f}° | "
                    f"{ac['bi_km']:.1f}km | {ac['fd_hz']:.0f}Hz |\n")

        f.write("\n## 匹配结果\n\n")
        if matches:
            f.write("| 航班 | PR距离 | PR多普勒 | PR_SNR | ADS-B | 水平距 | 高度 | 方位 | ADS-B多普勒 | 距离差 | 频差 |\n")
            f.write("|-----|--------|---------|--------|-------|-------|------|------|-----------|--------|------|\n")
            for m in matches:
                f.write(f"| {m['flight']} | {m['pr_range']:.1f}km | {m['pr_doppler']:+.0f}Hz | "
                        f"{m['pr_snr']:.1f}dB | {m['adsb_range']:.1f}km | {m['rx_dist_km']:.1f}km | "
                        f"{m['alt']} | {m['rx_bearing']:.0f}° | {m['adsb_doppler']:+.0f}Hz | "
                        f"{m['range_diff']:.1f}km | {m['doppler_diff']:.0f}Hz |\n")
        else:
            f.write("**无匹配**\n")

    log(f"报告: {report_file}")

    # 绘图
    plot_result(rk, dp, rd, peaks, f"pr_result_rsp1_{ts}.png")

    return matches, report_file, sample_time, process_start


def plot_result(rk, dp, rd, peaks, out_file):
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt

    caf_db = np.clip(rd, -25, 0)
    fig, ax = plt.subplots(figsize=(12, 7))
    extent = [rk[0], rk[-1], dp[0], dp[-1]]
    im = ax.imshow(caf_db, aspect='auto', origin='lower', extent=extent,
                   cmap='inferno', vmin=-20, vmax=0)

    if peaks:
        ax.scatter([p['range_km'] for p in peaks],
                   [p['doppler_hz'] for p in peaks],
                   c='lime', s=30, marker='o', edgecolors='black', linewidths=0.5)

    ax.set_xlabel('Range (km)')
    ax.set_ylabel('Doppler (Hz)')
    ax.set_title(f'PR Result (RSP1 {FREQ / 1e6:.1f}MHz, Ref={REF_TIME}s, LMS={M}taps)')
    plt.colorbar(im, ax=ax, label='dB')
    plt.tight_layout()
    plt.savefig(out_file, dpi=150)
    log(f"图像: {out_file}")
    plt.close()
    return out_file


# ---- 参数输出 ----

def print_config():
    """输出程序关键参数"""
    print("=" * 60)
    print("  FM-DDR -- RSP1 + Pi ADS-B")
    print("=" * 60)
    print(f"  [设备]      Windows RSP1 (SDRplay RSP1)")
    print(f"  [频率]      {FREQ / 1e6:.1f} MHz")
    print(f"  [采样率]    {FS / 1e6:.1f} MSPS")
    print(f"  [采集时长]  {DURATION} s")
    print(f"  [RSP1增益]  gRdB={RSP1_GRDB}")
    print(f"  [发射台]    ({TX_POS[0]:.3f}, {TX_POS[1]:.3f})")
    print(f"  [接收点]    ({RX_POS[0]:.3f}, {RX_POS[1]:.3f})")
    print(f"  [基线距]    {haversine(TX_POS[0], TX_POS[1], RX_POS[0], RX_POS[1]):.2f} km")
    print(f"  [处理参数]")
    print(f"       MAX_DELAY  = {MAX_DELAY}  (~{MAX_DELAY * 3e8 / FS / 1000:.0f} km)")
    print(f"       REF_TIME   = {REF_TIME} s  (多普勒分辨率 {1 / REF_TIME:.1f} Hz)")
    print(f"       DOPPLER    = +/-{DOPPLER_RANGE} Hz / {DOPPLER_BINS} bins")
    print(f"       LMS taps   = {M}  (mu={MU})")
    print(f"       MIN_SNR    = {MIN_SNR} dB")
    print(f"  [匹配阈值]  距离+/-{MATCH_RANGE_TOL}km, 多普勒+/-{MATCH_DOPPLER_TOL}Hz")
    print(f"  [ADS-B]     {PI} (readsb, 不中断服务)")
    print()


def main():
    print_config()

    # Step 1: ADS-B from Pi
    result = step1_adsb()
    if result is None:
        log("ADS-B获取失败，退出")
        return
    adsb_local, adsb_time = result

    # Step 2: RSP1 capture
    data_file = step2_rsp1()
    if data_file is None:
        log("RSP1采集失败，退出")
        return

    # Step 3: Process
    matches, report_file, sample_time, process_start = step3_process(data_file, adsb_local, adsb_time)

    # 摘要
    tx_rx_dist = haversine(TX_POS[0], TX_POS[1], RX_POS[0], RX_POS[1])
    print("\n" + "=" * 60)
    print("摘要")
    print("=" * 60)
    print(f"  设备:       RSP1 @ Windows")
    print(f"  FM频率:     {FREQ / 1e6:.1f} MHz")
    print(f"  MAX_DELAY:  {MAX_DELAY} (~{MAX_DELAY * 3e8 / FS / 1000:.0f} km)")
    print(f"  发射台:     ({TX_POS[0]:.3f}, {TX_POS[1]:.3f})")
    print(f"  接收点:     ({RX_POS[0]:.3f}, {RX_POS[1]:.3f})")
    print(f"  基线:       {tx_rx_dist:.2f} km")
    print(f"  采集时间:   {sample_time}")
    print(f"  ADS-B时间:  {adsb_time or '未知'}")
    print(f"  匹配:       {len(matches)} 个")
    if matches:
        for m in matches:
            print(f"    {m['flight']}: PR={m['pr_range']:.1f}km/{m['pr_doppler']:+.0f}Hz "
                  f"ADS-B={m['adsb_range']:.1f}km/{m['adsb_doppler']:+.0f}Hz "
                  f"(频差{m['doppler_diff']:.0f}Hz, 水平{m['rx_dist_km']:.1f}km, "
                  f"高度{m['alt']}ft, 方位{m['rx_bearing']:.0f}°)")
    else:
        print("  无匹配")
    print(f"  报告:       {os.path.abspath(report_file)}")

    # 清理临时文件
    for f in [data_file, adsb_local]:
        try:
            os.remove(f)
        except:
            pass

    print("=" * 60)


if __name__ == '__main__':
    main()
