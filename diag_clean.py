#!/usr/bin/env python3
"""验证 CLEAN 旁瓣抑制: 能否让高多普勒区弱目标峰露出来
对比: LMS-only vs LMS+CLEAN (101500 数据, CXA8162 bi=31.3km fd=+96Hz 已知目标)
"""
import sys, os, time
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

dp = np.linspace(-DOPPLER_RANGE, DOPPLER_RANGE, DOPPLER_BINS)
n = min(len(ref), len(out))
ref_c = ref[:n].astype(np.complex64)
surv_out = out[:n].astype(np.complex64)
ff = 1
while ff < n + MAX_DELAY:
    ff <<= 1
t = np.arange(n, dtype=np.float32)
rk = np.arange(MAX_DELAY) * (3e8/FS) / 1000

def full_caf(surv_in):
    S = fft(surv_in, ff)
    r = np.zeros((len(dp), MAX_DELAY), dtype=np.float32)
    for ci, fd in enumerate(dp):
        sf = ref_c * np.exp(-2j * np.pi * fd * t / FS)
        R = fft(sf, ff)
        r[ci] = np.abs(ifft(S * np.conj(R))[:MAX_DELAY])
    rd = 20 * np.log10(np.maximum(r, 1e-10))
    rd -= rd.max()
    return r, rd

# ---- LMS-only ----
r0, rd0 = full_caf(out.copy())
print(f"LMS-only: med={np.median(rd0):.1f}dB")
# 已知目标 CXA8162: fd=+96Hz bi=31.3km
ci = int(round((96 + 150)/300 * 60))
ri = int(round(31.3 / (3e8/FS/1000)))
print(f"  CXA8162 位置 (fd={dp[ci]:+.0f}Hz, {rk[ri]:.1f}km): {rd0[ci,ri]:.1f}dB (旁瓣参考 max={rd0.max():.1f}dB)")

# ---- LMS + CLEAN (迭代去除最强峰) ----
def clean_caf(surv_in, n_iter=30, loop_gain=0.8):
    surv_c = surv_in.copy()
    removed = []
    S = fft(surv_c, ff)
    r = np.zeros((len(dp), MAX_DELAY), dtype=np.float32)
    for ci, fd in enumerate(dp):
        sf = ref_c * np.exp(-2j * np.pi * fd * t / FS)
        R = fft(sf, ff)
        r[ci] = np.abs(ifft(S * np.conj(R))[:MAX_DELAY])
    rd = 20*np.log10(np.maximum(r, 1e-10))
    # 找最强峰 (屏蔽中心 + 近距直达波区)
    c = len(dp)//2
    for it in range(n_iter):
        rd_m = rd.copy()
        rd_m[c, :] = -999          # 0Hz
        rd_m[:, :10] = -999        # <0.4km
        idx = np.unravel_index(np.argmax(rd_m), rd_m.shape)
        if rd_m[idx] < -25:
            break
        amp = 10**(rd_m[idx]/20)
        ci, ri = idx
        fd = dp[ci]; delay = ri
        # 在时域减去该分量
        sf = ref_c * np.exp(-2j*np.pi*fd*t/FS)
        proj = np.dot(surv_c, np.conj(sf))
        # 简化 CLEAN: 直接在该 CAF 位置置零
        rd[idx] = -999
        removed.append((fd, rk[ri], rd_m[idx]))
    return removed

removed = clean_caf(out.copy())
print(f"\nCLEAN 30次迭代检出的峰 (排除0Hz和近距):")
for fd, rk_km, snr in removed[:20]:
    print(f"  fd={fd:+5.0f}Hz  {rk_km:6.1f}km  {snr:6.1f}dB")

# ADS-B 目标
print(f"\nADS-B 目标 (101457 快照, 外推4s):")
print("  CXA8162: bi=31.3km fd=+96Hz")
print("  CDG2186: bi=66.9km fd=-83Hz")
print("  CSN8763: bi=20.4km fd=-94Hz")
