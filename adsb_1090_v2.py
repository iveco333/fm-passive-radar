#!/usr/bin/env python3
"""1090MHz ADS-B 重测: 修正采样率 + LO偏移 + DC阻挡 + 频谱/脉冲/解码"""
import sys, os, time
import numpy as np
import scipy.signal as sig
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from sdrplay_api import SDRplayAPI

FREQ = 1090e6
LO_OFFSET = 250e3      # LO 偏移 250kHz 避开 DC/LO 泄漏
FS_SET = 2.4e6          # bwType 选择 (实际 2.375M)
FS = 2.375e6            # 实测实际采样率
DURATION = 6.0
GAIN = 30

def main():
    sdr = SDRplayAPI()
    sdr.select_device(0)
    sdr.set_frequency(FREQ + LO_OFFSET)
    sdr.set_sample_rate(FS_SET)
    sdr.set_gain(GAIN)
    print(f"调谐 {FREQ/1e6:.0f}+{LO_OFFSET/1e3:.0f}kHz (实际采样率 {FS/1e6:.3f}M), 采 {DURATION}s", flush=True)
    iq = sdr.capture(DURATION)
    sdr.close()
    print(f"样本: {len(iq)} = {len(iq)/FS:.2f}s", flush=True)

    # 数字下变频回 1090 + DC 阻挡
    t = np.arange(len(iq)) / FS
    iq_shift = iq * np.exp(-2j * np.pi * LO_OFFSET * t)
    b, a = sig.butter(2, 20e3 / (FS/2), 'high')
    iq_dc = sig.filtfilt(b, a, iq_shift)

    mag = np.abs(iq_dc)
    p99 = np.percentile(mag, 99)
    print(f"\nDC阻挡后: median={np.median(mag):.4f} p99={p99:.4f} max={mag.max():.4f}")
    print(f"动态范围: {20*np.log10(p99/np.median(mag)):.1f} dB", flush=True)

    # 频谱 1: 全带
    n_fft = 262144
    spec = 20*np.log10(np.abs(np.fft.fftshift(np.fft.fft(iq_dc[:n_fft] * np.hanning(n_fft)))) + 1e-12)
    freqs = (np.arange(n_fft) - n_fft/2) / n_fft * FS / 1e3
    pk = np.argmax(spec)
    print(f"最强分量: {freqs[pk]:+.0f} kHz @ {spec[pk]:.1f} dB (噪底 {np.median(spec):.1f})")

    # 频谱 2: 1090 中心 ±400kHz 的峰值分布 (ADS-B 信号特征)
    band = (freqs > -400) & (freqs < 400)
    spec_b = spec[band]
    fr_b = freqs[band]
    noise = np.median(spec_b)
    idx = np.argsort(spec_b)[-6:][::-1]
    print("中心±400kHz 最强分量:")
    for i in sorted(idx, key=lambda j: fr_b[j]):
        print(f"  {fr_b[i]:+7.1f} kHz  (+{spec_b[i]-noise:5.1f} dB)", flush=True)

    # 前导脉冲检测 (修正 bit 宽度 = 1us)
    bit = int(FS * 1e-6)   # 2375 samples/us
    thr = p99 * 0.8
    above = mag > thr
    n = len(mag)
    preambles = 0
    for i in range(200, n - 400):
        if not above[i]:
            continue
        try:
            if above[i+bit] and above[i+2*bit] and above[i+int(3.5*bit)]:
                if not above[i+bit//2] and not above[i+bit+bit//2] and not above[i+2*bit+bit//2]:
                    preambles += 1
        except IndexError:
            continue
    print(f"\n前导脉冲: {preambles}  ({len(iq)/FS:.1f}s 内)", flush=True)

    # 解码
    def decode_frame(sig_in, start, n_bits):
        bits = []
        for bb in range(n_bits):
            s = start + 8 * bit + bb * bit
            if s + bit >= len(sig_in):
                return None
            win = sig_in[s:s+bit]
            bits.append(1 if np.mean(win) > thr else 0)
        return "".join(str(x) for x in bits)

    try:
        import pyModeS as pms
        found = 0
        seen = {}
        for i in range(200, n - 400):
            if not above[i]:
                continue
            try:
                if above[i+bit] and above[i+2*bit] and above[i+int(3.5*bit)]:
                    if not above[i+bit//2] and not above[i+bit+bit//2] and not above[i+2*bit+bit//2]:
                        hx = decode_frame(mag, i, 112)
                        if hx:
                            try:
                                m = pms.Message(hx)
                                d = m.decode()
                                icao = d.get("icao", "?")
                                if icao not in seen:
                                    seen[icao] = 0
                                    cs = d.get("callsign", "-")
                                    alt = d.get("altitude", "-")
                                    print(f"  [{time.strftime('%H:%M:%S')}] {icao} {cs:>8s} {alt}ft", flush=True)
                                seen[icao] += 1
                                found += 1
                            except Exception:
                                pass
            except IndexError:
                continue
        print(f"\n解码: {found} 条, {len(seen)} 架飞机", flush=True)
    except ImportError:
        print("pyModeS 未安装, 跳过解码")

    # 保存 IQ
    iq_dc[:4000000].astype(np.complex64).tofile(os.path.join(os.path.dirname(os.path.abspath(__file__)), "adsb_1090_v2.bin"))
    print("已保存 adsb_1090_v2.bin")

if __name__ == "__main__":
    main()
