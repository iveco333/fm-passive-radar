#!/usr/bin/env python3
"""分析 1090MHz 泄漏峰形状: 窄带还是宽带? 能否频域挖掉?
如果泄漏是窄带峰, notch 掉后动态范围可大幅提升 -> 解码有望
"""
import sys, os, time
import numpy as np
import scipy.signal as sig
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from sdrplay_api import SDRplayAPI

FREQ = 1090e6
LO_OFFSET = 250e3
FS = 2.375e6
DURATION = 6.0
GAIN = 30

sdr = SDRplayAPI()
sdr.select_device(0)
sdr.set_frequency(FREQ + LO_OFFSET)
sdr.set_sample_rate(2.4e6)
sdr.set_gain(GAIN)
iq = sdr.capture(DURATION)
sdr.close()

t = np.arange(len(iq)) / FS
iq_shift = iq * np.exp(-2j * np.pi * LO_OFFSET * t)
b, a = sig.butter(2, 20e3 / (FS/2), 'high')
iq_dc = sig.filtfilt(b, a, iq_shift)
mag = np.abs(iq_dc)

# 频谱 (高分辨率看泄漏形状)
n_fft = 1048576
seg = iq_dc[:n_fft] * np.hanning(n_fft)
spec = 20*np.log10(np.abs(np.fft.fftshift(np.fft.fft(seg))) + 1e-12)
freqs = (np.arange(n_fft) - n_fft/2) / n_fft * FS / 1e3

# 找 -250kHz 附近峰值
pk_region = (freqs > -260) & (freqs < -240)
pk_idx = np.argmax(spec[pk_region])
pk_f = freqs[pk_region][pk_idx]
pk_db = spec[pk_region][pk_idx]
noise_db = np.median(spec)
print(f"泄漏峰: {pk_f:+.1f} kHz, {pk_db-noise_db:+.1f} dB 高于噪底")

# 泄漏峰宽度 (-3dB / -20dB / -40dB)
def width_at(db_below):
    thr = pk_db - db_below
    band = np.abs(freqs - pk_f) < 400
    fb = freqs[band]
    in_band = spec[band] > thr
    if in_band.any():
        return fb[in_band].max() - fb[in_band].min()
    return 0
print(f"-3dB 宽度: {width_at(3):.2f} kHz")
print(f"-20dB 宽度: {width_at(20):.2f} kHz")
print(f"-40dB 宽度: {width_at(40):.2f} kHz")

# 频域挖掉泄漏峰
notch_lo, notch_hi = pk_f - 10, pk_f + 10
f_all = np.fft.fftshift(np.fft.fftfreq(n_fft, 1/FS)) / 1e3
spec_masked = spec.copy()
spec_masked[(f_all > notch_lo) & (f_all < notch_hi)] = -999
noise_masked = np.median(spec_masked[spec_masked > -900])
print(f"\n挖掉 {notch_lo:+.0f}~{notch_hi:+.0f}kHz 后:")
print(f"  剩余最强: {spec_masked.max():.1f} dB (噪底 {noise_masked:.1f})")
print(f"  动态范围: {spec_masked.max() - noise_masked:.1f} dB (原 {pk_db-noise_db:.1f} dB)")

# 时域实现: 频域挖掉 -> 逆变换 -> 前导脉冲/解码
spec_f = np.fft.fftshift(np.fft.fft(seg))
f_all_hz = np.fft.fftshift(np.fft.fftfreq(n_fft, 1/FS))
spec_f_masked = spec_f.copy()
spec_f_masked[(f_all_hz > notch_lo*1e3) & (f_all_hz < notch_hi*1e3)] = 0
iq_clean = np.fft.ifft(np.fft.ifftshift(spec_f_masked))

mag2 = np.abs(iq_clean)
p99 = np.percentile(mag2, 99)
dyn2 = 20*np.log10(p99/(np.median(mag2)+1e-12))
dyn_orig = 20*np.log10(np.percentile(mag, 99)/(np.median(mag)+1e-12))
print(f"\nnotch 后时域动态范围: {dyn2:.1f} dB (原始 {dyn_orig:.1f} dB)")

# 前导脉冲检测 (notch 后)
bit = int(FS*1e-6)
thr2 = p99 * 0.8
above = mag2 > thr2
n = len(mag2)
preambles = 0
for i in range(200, n-400):
    if not above[i]:
        continue
    try:
        if above[i+bit] and above[i+2*bit] and above[i+int(3.5*bit)]:
            if not above[i+bit//2] and not above[i+bit+bit//2] and not above[i+2*bit+bit//2]:
                preambles += 1
    except IndexError:
        continue
print(f"notch 后前导脉冲: {preambles}")

# 前导脉冲检测 (原始, 对照)
above0 = mag > thr2
p0 = 0
for i in range(200, n-400):
    if not above0[i]:
        continue
    try:
        if above0[i+bit] and above0[i+2*bit] and above0[i+int(3.5*bit)]:
            if not above0[i+bit//2] and not above0[i+bit+bit//2] and not above0[i+2*bit+bit//2]:
                p0 += 1
    except IndexError:
        continue
print(f"原始前导脉冲: {p0}")

# 保存 notch 后 IQ 供解码
iq_clean[:len(iq)].astype(np.complex64).tofile("adsb_notch.bin")
print("已保存 adsb_notch.bin")
