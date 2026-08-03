#!/usr/bin/env python3
"""用 notch 后的 IQ (adsb_notch.bin) 做完整 ADS-B 解码"""
import sys, os, time
import numpy as np
import scipy.signal as sig
import pyModeS as pms

FS = 2.375e6

iq = np.fromfile("adsb_notch.bin", dtype=np.complex64)
print(f"样本: {len(iq)} ({len(iq)/FS:.1f}s)")

# 再加强: 带通滤波 1090±1.5MHz (去掉远端杂散)
sos = sig.butter(5, [0.3e6, 1.0e6], 'band', fs=FS, output='sos')
iq = sig.sosfilt(sos, iq)

mag = np.abs(iq)
p99 = np.percentile(mag, 99)
print(f"median={np.median(mag):.4f} p99={p99:.4f} max={mag.max():.4f}")
print(f"动态范围: {20*np.log10(p99/np.median(mag)):.1f} dB")

bit = int(FS * 1e-6)
thr = p99 * 0.75

# 前导脉冲检测
above = mag > thr
n = len(mag)
preambles = []
for i in range(200, n-400):
    if not above[i]:
        continue
    try:
        if above[i+bit] and above[i+2*bit] and above[i+int(3.5*bit)]:
            if not above[i+bit//2] and not above[i+bit+bit//2] and not above[i+2*bit+bit//2]:
                preambles.append(i)
    except IndexError:
        continue
print(f"前导脉冲: {len(preambles)}")

# 去重 (间隔 > 4us)
dedup = []
last = -1000
for i in preambles:
    if i - last > 4*bit:
        dedup.append(i)
        last = i
print(f"去重后: {len(dedup)}")

def decode_frame(m, start, n_bits):
    bits = []
    for bb in range(n_bits):
        s = start + 8*bit + bb*bit
        if s + bit >= len(m):
            return None
        bits.append('1' if np.mean(m[s:s+bit]) > thr else '0')
    return ''.join(bits)

seen = {}
found = 0
for i in dedup:
    hx = decode_frame(mag, i, 112)
    if not hx:
        continue
    try:
        m = pms.Message(hx)
        d = m.decode()
        icao = d.get('icao', '?')
        if icao not in seen:
            seen[icao] = 0
            print(f"  [{time.strftime('%H:%M:%S')}] {icao} {d.get('callsign','-'):>8s} alt={d.get('altitude','-')} {d.get('gs','')}", flush=True)
        seen[icao] += 1
        found += 1
    except Exception:
        pass

print(f"\n解码: {found} 条, {len(seen)} 架飞机")
