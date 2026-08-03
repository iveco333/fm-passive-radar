#!/usr/bin/env python3
"""离线验证: CLEAN 移植效果对比 (LMS-only vs LMS+CLEAN)
用 101500/101537 两轮数据, 对比每个 ADS-B 目标位置附近的 CAF 峰
"""
import json, math, os, re, sys
import numpy as np
from scipy.fft import fft, ifft
from scipy import signal as sp_signal
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

FS = 2.375e6
M = 128
MU = 0.002
MAX_DELAY = 800
DOPPLER_RANGE = 150
DOPPLER_BINS = 61

# ---- CLEAN 参数 (从 pi_pr_v5 移植) ----
CLEAN_ITER = 30
CLEAN_SNR_MIN = 5.0        # 峰 SNR 低于此停止 (相对噪声中位)
CLEAN_ZERO_BINS = 2        # 0Hz ±N bins 屏蔽
CLEAN_DD_W = 4.0           # 高斯瓣宽度: 多普勒维
CLEAN_RR_W = 3.0           # 高斯瓣宽度: 距离维

def haversine(l1, o1, l2, o2):
    R = 6371
    a = math.sin(math.radians(l2-l1)/2)**2 + math.cos(math.radians(l1))*math.cos(math.radians(l2))*math.sin(math.radians(o2-o1)/2)**2
    return R*2*math.atan2(math.sqrt(a), math.sqrt(1-a))
def bearing(lat1, lon1, lat2, lon2):
    dlon = math.radians(lon2-lon1)
    lat1, lat2 = math.radians(lat1), math.radians(lat2)
    x = math.sin(dlon)*math.cos(lat2)
    y = math.cos(lat1)*math.sin(lat2) - math.sin(lat1)*math.cos(lat2)*math.cos(dlon)
    return (math.degrees(math.atan2(x, y))+360) % 360
TX_POS = (34.201, 108.954); RX_POS = (34.25, 108.94)
lam = 3e8/87.5e6
tx_rx = haversine(TX_POS[0], TX_POS[1], RX_POS[0], RX_POS[1])

def adsb_predict(json_file, extrap_sec):
    out = []
    with open(json_file) as f:
        adsb = json.load(f)
    for a in adsb.get('aircraft', []):
        if 'lat' not in a or 'lon' not in a: continue
        lat, lon = a['lat'], a['lon']
        gs = a.get('gs', 0); track = a.get('track', 0)
        alt_raw = a.get('alt_baro', '?')
        if gs <= 0: continue
        v = gs*0.514444
        dist_m = v * extrap_sec
        dlat = dist_m * math.cos(math.radians(track)) / 111320.0
        dlon = dist_m * math.sin(math.radians(track)) / (111320.0 * math.cos(math.radians(lat)) + 1e-9)
        lat += dlat; lon += dlon
        vx = v*math.sin(math.radians(track)); vy = v*math.cos(math.radians(track))
        tx_ground = haversine(TX_POS[0], TX_POS[1], lat, lon)
        rx_ground = haversine(RX_POS[0], RX_POS[1], lat, lon)
        alt_m = float(alt_raw)*0.3048 if alt_raw not in ('?', None) else 0
        tx_slant = math.sqrt(tx_ground**2 + (alt_m/1000)**2)
        rx_slant = math.sqrt(rx_ground**2 + (alt_m/1000)**2)
        bi = tx_slant + rx_slant - tx_rx
        brng_tx = bearing(TX_POS[0], TX_POS[1], lat, lon)
        brng_rx = bearing(RX_POS[0], RX_POS[1], lat, lon)
        cos_el_tx = tx_ground/tx_slant if tx_slant>0 else 1.0
        cos_el_rx = rx_ground/rx_slant if rx_slant>0 else 1.0
        tx_h = (math.sin(math.radians(brng_tx))*cos_el_tx, math.cos(math.radians(brng_tx))*cos_el_tx)
        rx_h = (math.sin(math.radians(brng_rx))*cos_el_rx, math.cos(math.radians(brng_rx))*cos_el_rx)
        fd = -(vx*(tx_h[0]+rx_h[0]) + vy*(tx_h[1]+rx_h[1])) / lam
        out.append((a.get('flight','?'), bi, fd, rx_ground))
    return out

def load_process(data_file):
    raw = np.fromfile(data_file, dtype=np.uint8)
    iq = (raw.astype(np.float32) - 127.5) / 127.5
    iq = iq[0::2] + 1j * iq[1::2]
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
    n_ref = int(1.0 * FS)
    frame_len = n_ref
    ref = iq[0:frame_len].astype(np.complex64)
    surv = iq[int(0.1*FS):int(0.1*FS)+frame_len].astype(np.complex64)
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
    return ref, out

def full_caf(ref, out):
    dp = np.linspace(-DOPPLER_RANGE, DOPPLER_RANGE, DOPPLER_BINS)
    n = min(len(ref), len(out))
    ref_c = ref[:n].astype(np.complex64)
    surv_out = out[:n].astype(np.complex64)
    ff = 1
    while ff < n + MAX_DELAY:
        ff <<= 1
    t = np.arange(n, dtype=np.float32)
    rk = np.arange(MAX_DELAY) * (3e8/FS) / 1000
    S = fft(surv_out, ff)
    r = np.zeros((len(dp), MAX_DELAY), dtype=np.float32)
    for ci, fd in enumerate(dp):
        sf = ref_c * np.exp(-2j * np.pi * fd * t / FS)
        R = fft(sf, ff)
        r[ci] = np.abs(ifft(S * np.conj(R))[:MAX_DELAY])
    rd = 20 * np.log10(np.maximum(r, 1e-10))
    rd -= rd.max()
    return dp, rk, rd

def clean_peaks(rd, dp, rk):
    """CLEAN: 迭代找峰, 减高斯旁瓣 (移植自 pi_pr_v5)"""
    amp = 10 ** (rd / 20.0)
    amp_clean = amp.copy()
    c = len(dp) // 2
    # 屏蔽 0Hz 直达波区
    amp_clean[max(0,c-CLEAN_ZERO_BINS):c+CLEAN_ZERO_BINS+1, :] = 0
    # 屏蔽近距 <0.5km
    amp_clean[:, :4] = 0
    # 屏蔽超远 >100km
    amp_clean[:, 800:] = 0

    mask_pos = amp_clean > 0
    noise_med = np.median(amp_clean[mask_pos]) if mask_pos.any() else 1e-12
    peaks = []
    for it in range(CLEAN_ITER):
        idx = np.argmax(amp_clean)
        di, ri = np.unravel_index(idx, amp_clean.shape)
        pv = amp_clean[di, ri]
        if pv <= 0:
            break
        snr = 20 * np.log10(pv / (noise_med + 1e-12))
        if snr < CLEAN_SNR_MIN:
            break
        peaks.append({'range_km': float(rk[ri]), 'doppler_hz': float(dp[di]),
                      'snr_db': float(rd[di, ri]), 'snr_clean': snr})
        # 高斯瓣相减
        dd = (np.arange(len(dp))[:, np.newaxis] - di) / CLEAN_DD_W
        rr = (np.arange(len(rk))[np.newaxis, :] - ri) / CLEAN_RR_W
        lobe = pv * np.exp(-(dd**2 + rr**2))
        amp_clean -= lobe
        np.clip(amp_clean, 0, None, out=amp_clean)
    peaks.sort(key=lambda p: -p['snr_clean'])
    return peaks

def probe_target(rd, fd, bi):
    """在 CAF 上目标预测位置 (fd±3bin, bi±10km) 找最强峰"""
    dp = np.linspace(-DOPPLER_RANGE, DOPPLER_RANGE, DOPPLER_BINS)
    rk = np.arange(MAX_DELAY) * (3e8/FS) / 1000
    di = int(round((fd + DOPPLER_RANGE) / (2*DOPPLER_RANGE) * (DOPPLER_BINS-1)))
    di_lo, di_hi = max(0, di-3), min(DOPPLER_BINS-1, di+3)
    best = None
    for ci in range(di_lo, di_hi+1):
        row = rd[ci]
        pk = np.argmax(row)
        if rk[pk] < 80 and (best is None or row[pk] > best[2]):
            best = (rk[pk], dp[ci], row[pk])
    return best

# ---- 跑对比 ----
pairs = [
    ("fm_rsp1_20260803_101500.dat", "adsb_20260803_101457.json", 4),
    ("fm_rsp1_20260803_101537.dat", "adsb_20260803_101534.json", 3),
]

for dat, js, ext in pairs:
    print(f"\n{'='*72}\n{dat} + {js} (外推{ext}s)")
    ref, out = load_process(dat)
    dp, rk, rd = full_caf(ref, out)
    acs = adsb_predict(js, ext)
    peaks_clean = clean_peaks(rd, dp, rk)

    print(f"\n--- CLEAN 检出的峰 (前15, SNR>={CLEAN_SNR_MIN}dB) ---")
    print(f"{'#':>2} {'距离km':>7} {'多普勒Hz':>8} {'SNR':>6} {'cleanSNR':>8}")
    for i, p in enumerate(peaks_clean[:15]):
        print(f"{i:2d} {p['range_km']:7.1f} {p['doppler_hz']:+7.0f} {p['snr_db']:6.1f} {p['snr_clean']:8.1f}")

    print(f"\n--- ADS-B 目标 vs CLEAN 峰 (匹配: 距离±5km 多普勒±60Hz) ---")
    print(f"{'航班':>8} {'bi':>6} {'fd':>6} | {'CLEAN匹配':>20} {'状态':>6}")
    for fl, bi, fd, rx in acs:
        matched = None
        for p in peaks_clean:
            if abs(p['range_km'] - bi) <= 5.0 and abs(p['doppler_hz'] - fd) <= 60:
                matched = p
                break
        if matched:
            print(f"{fl:>8} {bi:6.1f} {fd:+5.0f} | {matched['range_km']:6.1f}km/{matched['doppler_hz']:+5.0f}Hz({matched['snr_clean']:4.1f}dB) [OK]")
        else:
            # 未匹配: 看目标位置原始 CAF 值
            probe = probe_target(rd, fd, bi)
            probe_s = f"{probe[0]:.1f}km/{probe[1]:+.0f}Hz({probe[2]:.1f}dB)" if probe else "无"
            print(f"{fl:>8} {bi:6.1f} {fd:+5.0f} | 未匹配 (CAF原始: {probe_s}) [NO]")

    # 假警统计: CLEAN 峰里没匹配任何 ADS-B 的
    matched_ranges = []
    for fl, bi, fd, rx in acs:
        for p in peaks_clean:
            if abs(p['range_km'] - bi) <= 5.0 and abs(p['doppler_hz'] - fd) <= 60:
                matched_ranges.append(p['range_km'])
    fa = sum(1 for p in peaks_clean if p['range_km'] not in matched_ranges)
    print(f"\n假警: {fa}/{len(peaks_clean)}")

