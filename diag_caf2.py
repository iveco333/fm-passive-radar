#!/usr/bin/env python3
"""验证: 屏蔽 0Hz 中心后, 高多普勒区能检出什么峰 (101500 数据, 5架飞机)"""
import sys, os, time
import numpy as np
from scipy.fft import fft, ifft
from scipy import signal as sp_signal
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

FS = 2.375e6
M = 128
MU = 0.002

raw = np.fromfile("fm_rsp1_20260803_101500.dat", dtype=np.uint8)
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

dp = np.linspace(-150, 150, 61)
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

r = np.zeros((len(dp), MAX_DELAY), dtype=np.float32)
for ci, fd in enumerate(dp):
    sf = ref_c * np.exp(-2j * np.pi * fd * t / FS)
    R = fft(sf, ff)
    r[ci] = np.abs(ifft(S * np.conj(R))[:MAX_DELAY])
rd = 20 * np.log10(np.maximum(r, 1e-10))
rd -= rd.max()
print(f"med={np.median(rd):.1f}dB  max={rd.max():.1f}dB")

# 峰值检测: 屏蔽 0Hz 中心 ±10Hz (更宽的屏蔽)
c = len(dp)//2
mask = np.ones_like(rd, dtype=bool)
mask[c-2:c+3, :] = False   # ±10Hz 屏蔽
rd_m = rd.copy()
rd_m[~mask] = -999

noise_med = np.median(rd[mask])
thr = noise_med + 5.0
print(f"噪声中位={noise_med:.1f}dB 阈值={thr:.1f}dB")

# 全局峰 (不看3x3, 直接找每多普勒bin的最大距离峰)
print(f"\n{'fd(Hz)':>7} {'距离(km)':>8} {'SNR(dB)':>8}")
for ci, fd in enumerate(dp):
    row = rd[ci]
    if not mask[ci].any():
        continue
    pk = np.argmax(row)
    if row[pk] > thr and rk[pk] < 60:
        print(f"{fd:+6.0f} {rk[pk]:8.1f} {row[pk]:8.1f}")

# 对比 ADS-B 预测 (fd, bi)
print("\nADS-B 预测:")
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
TX_POS = (34.201, 108.954); RX_POS = (34.25, 108.94)
lam = 3e8/87.5e6
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
    print(f"{a.get('flight','?'):>8}: bi={bi:5.1f}km fd={fd:+6.0f}Hz")
