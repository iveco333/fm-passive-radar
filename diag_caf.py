#!/usr/bin/env python3
"""诊断: 检查 CAF 高多普勒区能量分布 (为什么峰都集中在低多普勒?)
用 101500 那轮数据 (7架飞机, ADS-B多普勒 +97~130Hz / -83~-94Hz)
"""
import sys, os, time
import numpy as np
from scipy.fft import fft, ifft
from scipy import signal as sp_signal
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

FS = 2.375e6
M = 128
MU = 0.002
DOPPLER_RANGE = 150
DOPPLER_BINS = 61

# 加载数据
raw = np.fromfile("fm_rsp1_20260803_101500.dat", dtype=np.uint8)
iq = (raw.astype(np.float32) - 127.5) / 127.5
iq = iq[0::2] + 1j * iq[1::2]
print(f"样本: {len(iq)}")

# 预处理 (和主脚本一致)
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

# LMS
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
print("LMS 完成")

# CAF 全范围
dp = np.linspace(-DOPPLER_RANGE, DOPPLER_RANGE, DOPPLER_BINS)
MAX_DELAY = 800
n = min(len(ref), len(out))
ref_c = ref[:n].astype(np.complex64)
surv_out = out[:n].astype(np.complex64)
ff = 1
while ff < n + MAX_DELAY:
    ff <<= 1
S = fft(surv_out, ff)
t = np.arange(n, dtype=np.float32)
rk = np.arange(MAX_DELAY) * (3e8/FS) / 1000

# 逐 bin 算 (单进程慢点没关系)
r = np.zeros((len(dp), MAX_DELAY), dtype=np.float32)
for ci, fd in enumerate(dp):
    sf = ref_c * np.exp(-2j * np.pi * fd * t / FS)
    R = fft(sf, ff)
    r[ci] = np.abs(ifft(S * np.conj(R))[:MAX_DELAY])
    if ci % 15 == 0:
        print(f"  bin {ci}/{len(dp)} (fd={fd:+.0f}Hz) done", flush=True)

rd = 20 * np.log10(np.maximum(r, 1e-10))
rd -= rd.max()
print(f"\nCAF max={rd.max():.1f}dB  med={np.median(rd):.1f}dB")

# 按多普勒统计: 每 5Hz 区间的最大距离峰
print("\n=== 多普勒区间的最大 CAF 峰 ===")
print(f"{'fd区间':>10} {'最大峰(dB)':>10} {'距离(km)':>8}")
for lo in range(-150, 150, 15):
    mask = (dp >= lo) & (dp < lo + 15)
    if not mask.any():
        continue
    sub = rd[mask]
    idx = np.unravel_index(np.argmax(sub), sub.shape)
    dbi = np.where(mask)[0][idx[0]]
    print(f"{lo:+5d}~{lo+15:+4d}Hz  {sub.max():10.1f}  {rk[idx[1]]:7.1f}")

# ADS-B 预测的多普勒位置
print("\n=== ADS-B 预测 (外推到采集中间) ===")
import json, math
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
TX_POS = (34.201, 108.954)
RX_POS = (34.25, 108.94)
FREQ = 87.5e6
lam = 3e8/FREQ
tx_rx = haversine(TX_POS[0], TX_POS[1], RX_POS[0], RX_POS[1])
with open("adsb_20260803_101534.json") as f:
    adsb = json.load(f)
for a in adsb.get('aircraft', []):
    if 'lat' not in a or 'lon' not in a: continue
    lat, lon = a['lat'], a['lon']
    gs = a.get('gs', 0); track = a.get('track', 0)
    alt_raw = a.get('alt_baro', '?')
    v = gs * 0.514444
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
    print(f"{a.get('flight','?'):>8}: bi={bi:5.1f}km fd={fd:+6.0f}Hz gs={gs:3.0f} hdg={track:3.0f}")
