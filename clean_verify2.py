#!/usr/bin/env python3
"""CLEAN v2: 山脊核 (距离维宽核) 减直达波旁瓣
对比: 窄高斯核 vs 宽距离核
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

def clean_v2(rd, dp, rk, ridge=True, n_iter=40, snr_min=5.0, zero_bins=3):
    """CLEAN v2: 山脊核 - 减掉峰后, 沿距离维延伸核 (直达波旁瓣是距离山脊)"""
    amp = 10 ** (rd / 20.0)
    amp_clean = amp.copy()
    c = len(dp) // 2
    amp_clean[max(0,c-zero_bins):c+zero_bins+1, :] = 0
    amp_clean[:, :4] = 0
    amp_clean[:, 780:] = 0
    mask_pos = amp_clean > 0
    noise_med = np.median(amp_clean[mask_pos]) if mask_pos.any() else 1e-12
    peaks = []
    for it in range(n_iter):
        idx = np.argmax(amp_clean)
        di, ri = np.unravel_index(idx, amp_clean.shape)
        pv = amp_clean[di, ri]
        if pv <= 0: break
        snr = 20 * np.log10(pv / (noise_med + 1e-12))
        if snr < snr_min: break
        peaks.append({'range_km': float(rk[ri]), 'doppler_hz': float(dp[di]),
                      'snr_db': float(rd[di, ri]), 'snr_clean': snr})
        if ridge:
            # 山脊核: 多普勒维窄 (1.5 bins), 距离维宽 (40 bins ≈ 5km)
            dd = (np.arange(len(dp))[:, np.newaxis] - di) / 1.5
            rr = (np.arange(len(rk))[np.newaxis, :] - ri) / 40.0
        else:
            dd = (np.arange(len(dp))[:, np.newaxis] - di) / 4.0
            rr = (np.arange(len(rk))[np.newaxis, :] - ri) / 3.0
        lobe = pv * np.exp(-(dd**2 + rr**2))
        amp_clean -= lobe
        np.clip(amp_clean, 0, None, out=amp_clean)
    peaks.sort(key=lambda p: -p['snr_clean'])
    return peaks

pairs = [
    ("fm_rsp1_20260803_101500.dat", "adsb_20260803_101457.json", 4),
    ("fm_rsp1_20260803_101537.dat", "adsb_20260803_101534.json", 3),
]

for dat, js, ext in pairs:
    print(f"\n{'='*72}\n{dat} + {js}")
    ref, out = load_process(dat)
    dp, rk, rd = full_caf(ref, out)
    acs = adsb_predict(js, ext)

    for tag, ridge in [("窄高斯核", False), ("山脊核", True)]:
        peaks = clean_v2(rd, dp, rk, ridge=ridge)
        print(f"\n--- {tag} ---")
        print(f"{'航班':>8} {'bi':>6} {'fd':>6} | 匹配结果")
        for fl, bi, fd, rx in acs:
            matched = None
            for p in peaks:
                if abs(p['range_km'] - bi) <= 5.0 and abs(p['doppler_hz'] - fd) <= 60:
                    matched = p; break
            if matched:
                print(f"{fl:>8} {bi:6.1f} {fd:+5.0f} | {matched['range_km']:6.1f}km/{matched['doppler_hz']:+5.0f}Hz({matched['snr_clean']:4.1f}dB) [OK]")
            else:
                print(f"{fl:>8} {bi:6.1f} {fd:+5.0f} | [NO]")
        # 假警
        m = set()
        for fl, bi, fd, rx in acs:
            for p in peaks:
                if abs(p['range_km']-bi) <= 5.0 and abs(p['doppler_hz']-fd) <= 60:
                    m.add(p['range_km'])
        fa = sum(1 for p in peaks if p['range_km'] not in m)
        print(f"  峰数={len(peaks)} 假警={fa} ({fa*100//max(1,len(peaks))}%)")
