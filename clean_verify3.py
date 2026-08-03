#!/usr/bin/env python3
"""离线验证: 移植后的 CLEAN 在主程序配置下, 6轮数据的匹配效果
直接复用 pr_rsp1_parallel_multi 的模块函数
"""
import sys, os, json, math
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import numpy as np
from scipy.fft import fft, ifft
from scipy import signal as sp_signal

import pr_rsp1_parallel_multi as PR

FS = PR.FS
MAX_DELAY = PR.MAX_DELAY
DOPPLER_RANGE = PR.DOPPLER_RANGE
DOPPLER_BINS = PR.DOPPLER_BINS

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
    M_local = min(PR.M, ns // 4)
    rp = np.tile(ref, (ns // len(ref)) + 2)[:ns + M_local]
    w = np.zeros(M_local, dtype=np.complex64)
    out = surv.copy()
    B = 4096
    for i in range(0, ns, B):
        chunk = min(B, ns - i)
        for j in range(chunk):
            x = rp[i+j:i+j+M_local]
            e = out[i+j] - np.dot(w, x)
            w += PR.MU * e * np.conj(x)
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

# 6 轮配对
pairs = [
    ("fm_rsp1_20260803_101229.dat", "adsb_20260803_101226.json", 4),
    ("fm_rsp1_20260803_101307.dat", "adsb_20260803_101304.json", 5),
    ("fm_rsp1_20260803_101345.dat", "adsb_20260803_101342.json", 4),
    ("fm_rsp1_20260803_101423.dat", "adsb_20260803_101420.json", 3),
    ("fm_rsp1_20260803_101500.dat", "adsb_20260803_101457.json", 4),
    ("fm_rsp1_20260803_101537.dat", "adsb_20260803_101534.json", 3),
]

total_ac = 0
total_match = 0
total_fa = 0
total_peaks = 0

for dat, js, ext in pairs:
    print(f"\n{'='*70}\n{dat} + {js}")
    ref, out = load_process(dat)
    dp, rk, rd = full_caf(ref, out)
    peaks = PR.clean_peaks(rd, dp, rk)

    # 读取 ADS-B (复用主程序的匹配逻辑简化版)
    acs = []
    with open(js) as f:
        adsb = json.load(f)
    tx_rx = PR.haversine(PR.TX_POS[0], PR.TX_POS[1], PR.RX_POS[0], PR.RX_POS[1])
    lam = 3e8 / PR.FREQ
    for a in adsb.get('aircraft', []):
        if 'lat' not in a or 'lon' not in a: continue
        lat, lon = a['lat'], a['lon']
        gs = a.get('gs', 0); track = a.get('track', 0)
        alt_raw = a.get('alt_baro', '?')
        if gs <= 0: continue
        v = gs*0.514444
        dist_m = v * ext
        dlat = dist_m * math.cos(math.radians(track)) / 111320.0
        dlon = dist_m * math.sin(math.radians(track)) / (111320.0 * math.cos(math.radians(lat)) + 1e-9)
        lat += dlat; lon += dlon
        alt_m = float(alt_raw)*0.3048 if alt_raw not in ('?', None) else 0
        rx_ground = PR.haversine(PR.RX_POS[0], PR.RX_POS[1], lat, lon)
        tx_ground = PR.haversine(PR.TX_POS[0], PR.TX_POS[1], lat, lon)
        rx_slant = math.sqrt(rx_ground**2 + ((alt_m-PR.RX_ALT)/1000)**2)
        tx_slant = math.sqrt(tx_ground**2 + ((alt_m-PR.TX_ALT)/1000)**2)
        bi = tx_slant + rx_slant - tx_rx
        vx = v*math.sin(math.radians(track)); vy = v*math.cos(math.radians(track))
        brng_tx = PR.bearing(PR.TX_POS[0], PR.TX_POS[1], lat, lon)
        brng_rx = PR.bearing(PR.RX_POS[0], PR.RX_POS[1], lat, lon)
        cos_el_tx = tx_ground/tx_slant if tx_slant>0 else 1.0
        cos_el_rx = rx_ground/rx_slant if rx_slant>0 else 1.0
        tx_h = (math.sin(math.radians(brng_tx))*cos_el_tx, math.cos(math.radians(brng_tx))*cos_el_tx)
        rx_h = (math.sin(math.radians(brng_rx))*cos_el_rx, math.cos(math.radians(brng_rx))*cos_el_rx)
        fd = -(vx*(tx_h[0]+rx_h[0]) + vy*(tx_h[1]+rx_h[1])) / lam
        acs.append((a.get('flight','?'), bi, fd))

    n_match = 0
    print(f"{'航班':>8} {'bi':>6} {'fd':>6} | CLEAN匹配")
    for fl, bi, fd in acs:
        matched = None
        for p in peaks:
            if abs(p['range_km']-bi) <= PR.MATCH_RANGE_TOL and abs(p['doppler_hz']-fd) <= PR.MATCH_DOPPLER_TOL:
                matched = p; break
        if matched:
            n_match += 1
            print(f"{fl:>8} {bi:6.1f} {fd:+5.0f} | {matched['range_km']:5.1f}km/{matched['doppler_hz']:+5.0f}Hz [OK]")
        else:
            print(f"{fl:>8} {bi:6.1f} {fd:+5.0f} | [NO]")
    m_r = set()
    for fl, bi, fd in acs:
        for p in peaks:
            if abs(p['range_km']-bi) <= PR.MATCH_RANGE_TOL and abs(p['doppler_hz']-fd) <= PR.MATCH_DOPPLER_TOL:
                m_r.add(p['range_km'])
    fa = sum(1 for p in peaks if p['range_km'] not in m_r)
    total_ac += len(acs); total_match += n_match; total_fa += fa; total_peaks += len(peaks)
    print(f"  峰={len(peaks)} 匹配={n_match}/{len(acs)} 假警={fa}")

print(f"\n{'='*70}\n汇总: 目标 {total_ac}, 匹配 {total_match} ({total_match*100//max(1,total_ac)}%), 峰 {total_peaks}, 假警 {total_fa} ({total_fa*100//max(1,total_peaks)}%)")
