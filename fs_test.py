#!/usr/bin/env python3
"""测 RSP1 实际采样率: 同一信号两种假设 fs, 看 19kHz 导频显示位置
若显示位置 ∝ fs_assumed → 实际 fs 固定, 可反推; 若固定 → fs_assumed 正确"""
import sys, os
import numpy as np
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from sdrplay_api import SDRplayAPI

def find_pilot(audio, fs, lo=10e3, hi=30e3):
    seg = audio - np.mean(audio)
    n = len(seg)
    win = np.hanning(n)
    spec = np.abs(np.fft.fftshift(np.fft.fft(seg * win)))
    spec_db = 20*np.log10(spec + 1e-12)
    freqs = np.linspace(-fs/2, fs/2, n)
    pos = (freqs > lo) & (freqs < hi)
    band_db = spec_db[pos]
    band_f = freqs[pos]
    pk = np.argmax(band_db)
    return band_f[pk], band_db[pk] - np.median(spec_db)

def main():
    sdr = SDRplayAPI()
    sdr.select_device(0)
    sdr.set_frequency(88e6)
    sdr.set_gain(40)

    for fs_assumed in [1.94e6, 2.4e6]:
        sdr.set_sample_rate(fs_assumed)
        iq = sdr.capture(3.0)
        audio = np.diff(np.unwrap(np.angle(iq)))
        f_pilot, over = find_pilot(audio, fs_assumed)
        print(f"假设 fs={fs_assumed/1e6:.2f}M: 导频峰显示 {f_pilot/1e3:6.2f} kHz (+{over:.0f}dB)"
              f"  反推实际fs={fs_assumed*19e3/f_pilot/1e6:.3f}M", flush=True)
        # 也打印最强的几个峰
        seg = audio - np.mean(audio)
        n = len(seg)
        spec = np.abs(np.fft.fftshift(np.fft.fft(seg*np.hanning(n))))
        spec_db = 20*np.log10(spec+1e-12)
        freqs = np.linspace(-fs_assumed/2, fs_assumed/2, n)
        pos = freqs > 0
        idx = np.argsort(spec_db[pos])[-5:][::-1]
        print("   峰:", "  ".join(f"{freqs[pos][i]/1e3:.1f}k({spec_db[pos][i]-np.median(spec_db):+.0f})" for i in sorted(idx, key=lambda j: freqs[pos][j])), flush=True)
    sdr.close()

if __name__ == "__main__":
    main()
