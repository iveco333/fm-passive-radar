#!/usr/bin/env python3
"""ADS-B 深度尝试: 匹配滤波 + 前导脉冲精检 + pyModeS 解码
采集 20s, 提高检出机会
"""
import sys, os, time
import numpy as np
import scipy.signal as sig
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from sdrplay_api import SDRplayAPI

FREQ = 1090e6
LO_OFFSET = 250e3
FS = 2.375e6
DURATION = 20.0
GAIN = 30

print(f"调谐 {FREQ/1e6:.0f}+{LO_OFFSET/1e3:.0f}kHz, gRdB={GAIN}, 采 {DURATION}s", flush=True)
sdr = SDRplayAPI()
sdr.select_device(0)
sdr.set_frequency(FREQ + LO_OFFSET)
sdr.set_sample_rate(2.4e6)
sdr.set_gain(GAIN)
iq = sdr.capture(DURATION)
sdr.close()
print(f"样本: {len(iq)} ({len(iq)/FS:.1f}s)", flush=True)

t = np.arange(len(iq)) / FS
iq_shift = iq * np.exp(-2j * np.pi * LO_OFFSET * t)
b, a = sig.butter(2, 20e3 / (FS/2), 'high')
iq_dc = sig.filtfilt(b, a, iq_shift)
mag = np.abs(iq_dc)

p99 = np.percentile(mag, 99)
print(f"median={np.median(mag):.4f} p99={p99:.4f} max={mag.max():.4f} 动态范围={20*np.log10(p99/np.median(mag)):.1f}dB", flush=True)

bit = int(FS * 1e-6)   # 1us = 2375 samples
thr = p99 * 0.75

# 匹配滤波: 前导脉冲模板 (1,0,1,0 各1us, 间隔1us: 位置 0,1,2,3.5us)
tpl = np.zeros(int(4.5*bit), dtype=np.float32)
tpl[0:bit] = 1.0
tpl[2*bit:3*bit] = 1.0
# 用滑动相关找前导
corr = np.convolve(mag[:], tpl[::-1], mode='same')
corr_norm = corr / (np.convolve(np.ones_like(mag), np.ones_like(tpl), mode='same') + 1e-9)

# 找相关峰
pk_thr = corr_norm.max() * 0.5
cand = np.where(corr_norm > pk_thr)[0]
print(f"匹配滤波: 相关峰阈值 {pk_thr:.4f}, 候选 {len(cand)}", flush=True)

# 在候选中严格验证前导 + 解码
def decode_frame(m, start, n_bits):
    bits = []
    for bb in range(n_bits):
        s = start + 8*bit + bb*bit
        if s + bit >= len(m): return None
        bits.append('1' if np.mean(m[s:s+bit]) > thr else '0')
    return ''.join(bits)

import pyModeS as pms
seen = {}
found = 0
checked = 0
# 去重候选 (间隔 > 3us)
cands_dedup = []
last = -1000
for i in cand:
    if i - last > 3*bit:
        cands_dedup.append(i)
        last = i

print(f"去重后候选: {len(cands_dedup)}", flush=True)
for i in cands_dedup:
    if i < 200 or i > len(mag) - 400: continue
    # 严格前导: 高-低-高-低 时序
    try:
        ok = (mag[i] > thr and mag[i+bit] < thr*0.7 and
              mag[i+2*bit] > thr and mag[i+3*bit] < thr*0.7 and
              mag[i+int(3.5*bit)] > thr)
    except IndexError:
        continue
    if not ok: continue
    checked += 1
    hx = decode_frame(mag, i, 112)
    if hx:
        try:
            m = pms.Message(hx)
            d = m.decode()
            icao = d.get('icao', '?')
            if icao not in seen:
                seen[icao] = 0
                cs = d.get('callsign', '-')
                alt = d.get('altitude', '-')
                print(f"  [{time.strftime('%H:%M:%S')}] {icao} {cs:>8s} alt={alt}", flush=True)
            seen[icao] += 1
            found += 1
        except Exception:
            pass

print(f"\n严格前导通过: {checked}, 解码: {found} 条, {len(seen)} 架飞机")
