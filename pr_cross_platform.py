#!/usr/bin/env python3
"""
FM被动雷达 — 跨平台一键执行脚本
Pi采集 + Windows处理，自动匹配ADS-B

用法: python pr_cross_platform.py
"""
import os, sys, time, subprocess, datetime, json, math
import numpy as np
from scipy.fft import fft, ifft
from scipy import signal as sp_signal

# ========== 配置 ==========
PI = "iveco@172.20.10.8"
PI_SCRIPTS = "/tmp"
FREQ = 91.6e6
FS = 2.0e6
GAIN = 25
DURATION = 4
NSAMP = int(FS * DURATION)

# 处理参数
REF_TIME = 1.0
SURV_TIME = 1.0
MAX_DELAY = 600
DOPPLER_RANGE = 100
DOPPLER_BINS = 41
M = 128  # LMS taps
MU = 0.002

# 匹配阈值
MATCH_RANGE_TOL = 5.0
MATCH_DOPPLER_TOL = 40
MIN_SNR = -6

# 位置
RX_POS = (34.25, 108.94)
TX_POS = (34.201, 108.954)

# 站点高度（米，近似值，不影响太大）
RX_ALT = 0    # 接收机地面高度
TX_ALT = 0    # 发射台地面高度

def log(msg):
    print(f"[{time.strftime('%H:%M:%S')}] {msg}")

def run(cmd, timeout=300):
    """执行命令 - 实时输出"""
    print(f"  $ {cmd}")
    process = subprocess.Popen(cmd, shell=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                               text=True, encoding='utf-8', errors='replace', bufsize=1)
    
    # 实时输出stdout和stderr
    try:
        for line in iter(process.stdout.readline, ''):
            if line:
                print(line.rstrip())
    except KeyboardInterrupt:
        process.terminate()
        raise
    
    # 等待完成
    process.wait(timeout=timeout)
    
    return process.returncode == 0

def step1_pi_record():
    """Step 1: Pi采集数据"""
    log("Step 1: Pi采集数据")
    
    # 创建Pi端采集脚本
    pi_script = f"""#!/usr/bin/env python3
import subprocess, time, datetime

def log(msg):
    print(f"[{{datetime.datetime.now().strftime('%H:%M:%S')}}] {{msg}}", flush=True)

log("=== 开始采集流程 ===")

# 清理旧数据
log("[清理] 删除旧的FM数据文件")
subprocess.run("rm -f /tmp/fm_data.dat", shell=True)

# 保存ADS-B快照 (1090 MHz)
log("[ADS-B 1090MHz] 保存飞机快照到 /tmp/adsb_snapshot.json")
subprocess.run("cp /run/readsb/aircraft.json /tmp/adsb_snapshot.json", shell=True)
log("[ADS-B 1090MHz] 快照完成 - 包含当前空域飞机位置/速度/航向")

# 停止readsb
log("[ADS-B 1090MHz] 停止 readsb 服务 (释放RTL-SDR)")
subprocess.run("sudo systemctl stop readsb", shell=True)
time.sleep(2)

# 采集FM数据 (91.6 MHz)
log("[FM 91.6MHz] === 开始被动雷达采样 ===")
log("[FM 91.6MHz] 频段: FM广播 91.6 MHz | 采样率: 2.0 MSPS | 时长: 4秒")
cmd = "rtl_sdr -f {FREQ:.0f} -s {FS:.0f} -n {NSAMP} -g {GAIN} /tmp/fm_data.dat"
log(f"[FM 91.6MHz] 执行: {{cmd}}")
result = subprocess.run(cmd, shell=True, capture_output=True, text=True)
if result.returncode != 0:
    log("[FM 91.6MHz] 采集失败!")
    exit(1)
log("[FM 91.6MHz] === 被动雷达采样完成 ===")
log("[FM 91.6MHz] 数据保存到: /tmp/fm_data.dat")

# 重启readsb
log("[ADS-B 1090MHz] 重启 readsb 服务")
subprocess.run("sudo mkdir -p /run/readsb && sudo systemctl start readsb", shell=True)
log("=== 采集流程完成 ===")
log("[总结] ADS-B(1090MHz)快照 + FM(91.6MHz)采样 已完成")
"""
    
    # 写入Pi
    with open("pi_record.py", "w", encoding="utf-8") as f:
        f.write(pi_script)
    
    if not run(f"scp pi_record.py {PI}:/tmp/pi_record.py"):
        return False
    
    log("[Pi] 执行采集脚本...")
    if not run(f"ssh {PI} \"python3 /tmp/pi_record.py\""):
        return False
    
    log("[Pi] 采集完成")
    return True

def step2_download():
    """Step 2: 下载数据"""
    log("Step 2: 下载数据到Windows")
    log("[传输] 开始从Pi传输数据到Windows...")
    transfer_start = time.strftime('%H:%M:%S')
    
    ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    data_file = f"fm_data_{ts}.dat"
    adsb_file = f"adsb_{ts}.json"
    
    log(f"[传输] 开始下载FM数据: {PI}:/tmp/fm_data.dat -> ./{data_file}")
    if not run(f"scp {PI}:/tmp/fm_data.dat ./{data_file}"):
        return None, None, None
    log(f"[传输] FM数据下载完成: {os.path.abspath(data_file)}")
    
    log(f"[传输] 开始下载ADS-B数据: {PI}:/tmp/adsb_snapshot.json -> ./{adsb_file}")
    if not run(f"scp {PI}:/tmp/adsb_snapshot.json ./{adsb_file}"):
        return None, None, None
    log(f"[传输] ADS-B数据下载完成: {os.path.abspath(adsb_file)}")
    
    transfer_end = time.strftime('%H:%M:%S')
    log(f"[传输] 传输开始: {transfer_start} | 传输完成: {transfer_end}")
    
    # 获取ADS-B数据时间戳（用文件修改时间，因为是在采集前复制的）
    adsb_time = None
    try:
        # 先尝试从JSON里的now字段获取
        with open(adsb_file, 'r') as f:
            adsb_data = json.load(f)
            adsb_now = adsb_data.get('now', None)
            if adsb_now:
                adsb_time = datetime.datetime.fromtimestamp(adsb_now).strftime('%Y-%m-%d %H:%M:%S')
        
        # 如果JSON里没有或时间差太大，用文件修改时间
        file_mtime = os.path.getmtime(adsb_file)
        file_time = datetime.datetime.fromtimestamp(file_mtime).strftime('%Y-%m-%d %H:%M:%S')
        
        # 如果JSON时间比文件时间早很多（超过5分钟），用文件时间
        if adsb_time and abs(file_mtime - adsb_now) > 300:
            adsb_time = file_time + " (文件时间)"
        elif not adsb_time:
            adsb_time = file_time + " (文件时间)"
    except:
        pass
    
    return data_file, adsb_file, adsb_time

def step3_process(data_file, adsb_file, adsb_time=None):
    """Step 3: Windows处理"""
    log("Step 3: Windows处理 - 开始对比ADS-B数据")
    process_start = time.strftime('%H:%M:%S')
    log(f"[处理] 数据处理开始时间: {process_start}")
    
    ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    
    # 从文件名提取采样时间
    sample_time_str = data_file[8:21]  # YYYYMMDD_HHMMSS
    try:
        sample_time = datetime.datetime.strptime(sample_time_str, "%Y%m%d_%H%M%S").strftime('%Y-%m-%d %H:%M:%S')
    except:
        sample_time = "未知"
    
    log(f"[处理] 数据文件: {data_file}")
    log(f"[处理] 文件创建时间(Windows下载时间): {sample_time}")
    log(f"[处理] ADS-B快照时间: {adsb_time if adsb_time else '未知'}")
    log(f"[处理] 处理内容: 1)加载IQ数据 2)预处理(直流抑制/陷波/低通) 3)LMS自适应滤波(DPI抑制) 4)CAF互模糊函数计算 5)峰值检测 6)与ADS-B数据匹配")
    
    # 加载数据
    log("[处理1/6] 加载IQ数据...")
    raw = np.fromfile(data_file, dtype=np.uint8)
    iq = (raw.astype(np.float32) - 127.5) / 127.5
    iq = iq[0::2] + 1j * iq[1::2]
    log(f"  {len(iq)} 样本 ({len(iq)/FS:.1f}s)")
    
    # 预处理
    log("[处理2/6] 预处理(直流抑制 + 19kHz陷波 + 100kHz低通)...")
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
    
    # 分割通道
    n_ref = int(REF_TIME * FS)
    n_surv = int(SURV_TIME * FS)
    ref = iq[:n_ref]
    surv = iq[int(0.1*FS):int(0.1*FS)+n_surv]
    
    # LMS DPI
    log(f"[处理3/6] LMS自适应滤波(DPI抑制, {M} taps)...")
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
    
    log(f"  完成. 残差: {np.mean(np.abs(out)):.4f}")
    out = out / (np.sqrt(np.mean(np.abs(out)**2)) + 1e-10)
    
    # CAF
    log("[处理4/6] CAF互模糊函数计算...")
    log(f"[处理4/6] 多普勒范围: ±{DOPPLER_RANGE}Hz, 分辨率: {1/REF_TIME:.1f}Hz/bin")
    n = min(len(ref), len(out))
    ref = ref[:n]
    surv = out[:n]
    
    dp = np.linspace(-DOPPLER_RANGE, DOPPLER_RANGE, DOPPLER_BINS)
    ff = 1
    while ff < n + MAX_DELAY: ff <<= 1
    
    r = np.zeros((len(dp), MAX_DELAY), dtype=np.float32)
    t = np.arange(n, dtype=np.float32)
    
    for di, fd in enumerate(dp):
        if di % 5 == 0:
            log(f"  Doppler {di+1}/{len(dp)} ({fd:+.0f} Hz)")
        sf = ref * np.exp(-2j * np.pi * fd * t / FS)
        S = fft(surv, ff)
        R = fft(sf, ff)
        r[di] = np.abs(ifft(S * np.conj(R))[:MAX_DELAY])
    
    rk = np.arange(MAX_DELAY) * (3e8/FS) / 1000
    rd = 20 * np.log10(np.maximum(r, 1e-10))
    rd -= rd.max()
    
    # 提取峰值
    c = len(dp) // 2
    mk = np.ones_like(rd, dtype=bool)
    mk[c-1:c+2, :] = False
    
    peaks = []
    fl = rd[mk]
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
    
    log(f"[处理5/6] 峰值检测: 找到 {len(peaks)} 个峰值")
    
    # 加载ADS-B
    log("[处理5/6] 加载ADS-B数据...")
    with open(adsb_file, 'r') as f:
        adsb_data = json.load(f)
    
    # 计算双基地距离和多普勒
    tx_rx = haversine(TX_POS[0], TX_POS[1], RX_POS[0], RX_POS[1])
    lam = 3e8 / FREQ
    
    def bearing(lat1, lon1, lat2, lon2):
        """计算从点1到点2的方位角（度）"""
        dlon = math.radians(lon2 - lon1)
        lat1, lat2 = math.radians(lat1), math.radians(lat2)
        x = math.sin(dlon) * math.cos(lat2)
        y = math.cos(lat1) * math.sin(lat2) - math.sin(lat1) * math.cos(lat2) * math.cos(dlon)
        brng = math.atan2(x, y)
        return (math.degrees(brng) + 360) % 360
    
    aircraft = []
    for a in adsb_data.get('aircraft', []):
        if 'lat' not in a or 'lon' not in a:
            continue
        lat, lon = a['lat'], a['lon']
        gs = a.get('gs', 0)  # 地速，节
        track = a.get('track', 0)  # 航向，度
        alt_raw = a.get('alt_baro', '?')
        flight = a.get('flight', '?').strip()
        
        # 解析高度（英尺转米）
        if alt_raw != '?' and alt_raw is not None and alt_raw != 'ground':
            alt_m = float(alt_raw) * 0.3048  # 英尺转米
            alt_display = alt_raw
        else:
            alt_m = 0
            alt_display = '?'
        
        # 水平地面距离 (km)
        rx_ground = haversine(RX_POS[0], RX_POS[1], lat, lon)
        tx_ground = haversine(TX_POS[0], TX_POS[1], lat, lon)
        
        # 3D斜距 (km) — 考虑飞机高度
        rx_slant = math.sqrt(rx_ground**2 + ((alt_m - RX_ALT) / 1000)**2)
        tx_slant = math.sqrt(tx_ground**2 + ((alt_m - TX_ALT) / 1000)**2)
        bi = tx_slant + rx_slant - tx_rx  # 双基地距离用斜距
        
        # 双基地多普勒计算（3D修正）
        # 目标速度矢量 (航向是运动方向，只有水平分量)
        v = gs * 0.514444  # m/s
        # 航向转运动方向：track=0° 是北，90° 是东
        vx = v * math.sin(math.radians(track))  # 东向分量
        vy = v * math.cos(math.radians(track))  # 北向分量
        
        # 从发射机/接收机到目标的方位角
        brng_tx_to_tgt = bearing(TX_POS[0], TX_POS[1], lat, lon)
        brng_rx_to_tgt = bearing(RX_POS[0], RX_POS[1], lat, lon)
        
        # 俯仰角余弦：cos(el) = ground_dist / slant_range
        # 速度只有水平方向，所以垂直分量点乘为0
        # 只需将水平单位向量乘以 cos(el) 即可
        cos_el_tx = tx_ground / tx_slant if tx_slant > 0 else 1.0
        cos_el_rx = rx_ground / rx_slant if rx_slant > 0 else 1.0
        
        # 水平单位向量（从发射机/接收机指向目标），已乘俯仰角修正
        tx_h = (math.sin(math.radians(brng_tx_to_tgt)) * cos_el_tx,
                math.cos(math.radians(brng_tx_to_tgt)) * cos_el_tx)
        rx_h = (math.sin(math.radians(brng_rx_to_tgt)) * cos_el_rx,
                math.cos(math.radians(brng_rx_to_tgt)) * cos_el_rx)
        
        # 双基地多普勒 = -v · (tx_h + rx_h) / lambda
        # 负号：目标靠近时多普勒为正
        # tx_h/rx_h 已经包含 cos(el) 修正
        fd = -(vx * (tx_h[0] + rx_h[0]) + vy * (tx_h[1] + rx_h[1])) / lam
        
        # 计算目标相对于接收机的方位
        brng_from_rx = bearing(RX_POS[0], RX_POS[1], lat, lon)
        
        aircraft.append({
            'flight': flight,
            'alt': alt_display,
            'gs': gs,
            'track': track,
            'bi_km': bi,
            'fd_hz': fd,
            'rx_dist_km': rx_ground,  # 水平距离
            'rx_slant_km': rx_slant,  # 斜距
            'rx_bearing': brng_from_rx
        })
    
    log(f"  ADS-B飞机: {len(aircraft)} 架")
    
    # 匹配
    log("[处理6/6] 匹配PR检测峰值与ADS-B数据...")
    log(f"[处理6/6] 匹配阈值: 距离±{MATCH_RANGE_TOL}km, 多普勒±{MATCH_DOPPLER_TOL}Hz")
    matches = []
    for peak in peaks:
        for ac in aircraft:
            r_diff = abs(peak['range_km'] - ac['bi_km'])
            d_diff = abs(peak['doppler_hz'] - ac['fd_hz'])
            if r_diff <= MATCH_RANGE_TOL and d_diff <= MATCH_DOPPLER_TOL:
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
                    'rx_bearing': ac['rx_bearing'],
                    'alt': ac['alt']
                })
    
    # 去重
    seen = set()
    unique = []
    for m in sorted(matches, key=lambda x: x['range_diff'] + x['doppler_diff']/10):
        if m['flight'] not in seen:
            seen.add(m['flight'])
            unique.append(m)
    
    log(f"  匹配: {len(unique)} 个")
    if unique:
        for m in unique:
            log(f"  [匹配] {m['flight']}: PR={m['pr_range']:.1f}km/{m['pr_doppler']:+.0f}Hz(SNR{m['pr_snr']:.1f}dB) vs ADS-B={m['adsb_range']:.1f}km/{m['adsb_doppler']:+.0f}Hz (频差{m['doppler_diff']:.0f}Hz, 水平距我{m['rx_dist_km']:.1f}km, 高度{m['alt']}ft, 方位{m['rx_bearing']:.0f}°)")
    else:
        log("  [对比] 无匹配目标")
    
    # 生成报告
    report_file = f"pr_report_{ts}.md"
    process_time = time.strftime('%Y-%m-%d %H:%M:%S')
    process_end = time.strftime('%H:%M:%S')
    log(f"[处理] 数据处理完成时间: {process_end}")
    
    with open(report_file, 'w') as f:
        f.write("# PR vs ADS-B 对照报告\n\n")
        f.write(f"**采样时间**: {sample_time}\n")
        f.write(f"**ADS-B数据时间**: {adsb_time if adsb_time else '未知'}\n")
        f.write(f"**处理时间**: {process_time}\n")
        f.write(f"**频率**: {FREQ/1e6:.1f} MHz\n")
        f.write(f"**参考时长**: {REF_TIME} s\n")
        f.write(f"**多普勒分辨率**: {1/REF_TIME:.1f} Hz/bin\n")
        f.write(f"**LMS taps**: {M}\n\n")
        
        f.write("## PR检测峰值 (Top 20)\n\n")
        f.write("| 距离(km) | 多普勒(Hz) | SNR(dB) |\n")
        f.write("|---------|-----------|--------|\n")
        for p in peaks[:20]:
            f.write(f"| {p['range_km']:.1f} | {p['doppler_hz']:+.0f} | {p['snr_db']:.1f} |\n")
        
        f.write("\n## ADS-B 飞机\n\n")
        f.write("| 航班 | 高度(ft) | 速度(kts) | 航向 | 距我(水平) | 距我(斜距) | 方位 | 双基地距离(斜距) | 多普勒(3D) |\n")
        f.write("|-----|---------|-----------|------|-----------|----------|------|-----------------|----------|\n")
        for ac in sorted(aircraft, key=lambda x: x['bi_km']):
            f.write(f"| {ac['flight']} | {ac['alt']} | {ac['gs']:.0f} | {ac['track']:.0f}° | {ac['rx_dist_km']:.1f}km | {ac.get('rx_slant_km', ac['rx_dist_km']):.1f}km | {ac['rx_bearing']:.0f}° | {ac['bi_km']:.1f} km | {ac['fd_hz']:.0f} Hz |\n")
        
        f.write("\n## 匹配结果\n\n")
        if unique:
            f.write("| 航班 | PR距离 | PR多普勒 | PR_SNR | ADS-B斜距 | 距我(水平) | 高度 | 方位 | ADS-B多普勒(3D) | 距离差 | 频差 |\n")
            f.write("|-----|--------|---------|--------|----------|-----------|------|------|---------------|--------|------|\n")
            for m in unique:
                f.write(f"| {m['flight']} | {m['pr_range']:.1f}km | {m['pr_doppler']:+.0f}Hz | {m['pr_snr']:.1f}dB | ")
                f.write(f"{m['adsb_range']:.1f}km | {m['rx_dist_km']:.1f}km | {m.get('alt','?')} | {m['rx_bearing']:.0f}° | {m['adsb_doppler']:+.0f}Hz | {m['range_diff']:.1f}km | {m['doppler_diff']:.0f}Hz |\n")
        else:
            f.write("**无匹配**\n")
    
    log(f"报告已保存: {report_file}")
    
    # 绘制结果
    plot_result(rk, dp, rd, peaks, f"pr_result_{ts}.png")
    
    return unique, report_file, sample_time, process_start, process_end

def plot_result(rk, dp, rd, peaks, out_file):
    """绘制结果图"""
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
    ax.set_title(f'PR Result (91.6 MHz, Ref={REF_TIME}s, LMS={M}taps)')
    plt.colorbar(im, ax=ax, label='dB')
    plt.tight_layout()
    plt.savefig(out_file, dpi=150)
    log(f"图像已保存: {out_file}")

def haversine(l1, o1, l2, o2):
    R = 6371
    a = math.sin(math.radians(l2-l1)/2)**2 + math.cos(math.radians(l1))*math.cos(math.radians(l2))*math.sin(math.radians(o2-o1)/2)**2
    return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1-a))

def main():
    print("=" * 60)
    print("FM被动雷达 — 跨平台一键执行")
    print("=" * 60)
    
    # Step 1
    if not step1_pi_record():
        log("Pi采集失败，退出")
        return
    
    # Step 2
    data_file, adsb_file, adsb_time = step2_download()
    if not data_file:
        log("下载失败，退出")
        return
    
    # Step 3
    matches, report_file, sample_time, process_start, process_end = step3_process(data_file, adsb_file, adsb_time)
    
    # 摘要
    print("\n" + "=" * 60)
    print("摘要")
    print("=" * 60)
    print(f"数据文件: {data_file}")
    print(f"文件创建时间(Windows下载): {sample_time}")
    print(f"ADS-B快照时间: {adsb_time if adsb_time else '未知'}")
    print(f"数据处理时间: {process_start} - {process_end}")
    print(f"匹配: {len(matches)} 个")
    if matches:
        for m in matches:
            print(f"  {m['flight']}: PR={m['pr_range']:.1f}km/{m['pr_doppler']:+.0f}Hz "
                  f"ADS-B={m['adsb_range']:.1f}km/{m['adsb_doppler']:+.0f}Hz "
                  f"(水平距我{m['rx_dist_km']:.1f}km, 高度{m['alt']}ft, 方位{m['rx_bearing']:.0f}°)")
    else:
        print("  无匹配")
    print(f"\n报告: {os.path.abspath(report_file)}")
    print(f"数据: {os.path.abspath(data_file)}")
    print(f"ADS-B: {os.path.abspath(adsb_file)}")

if __name__ == '__main__':
    main()
