#!/usr/bin/env python3
"""验证 fsFreq.fsHz 设置是否真正控制采样率
设置 2.0M/2.4M/4.0M, 用 88MHz 台 19kHz 导频反推实际采样率"""
import sys, os
import numpy as np
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from sdrplay_api import SDRplayAPI

def find_pilot(audio, fs):
    seg = audio - np.mean(audio)
    n = len(seg)
    spec = np.abs(np.fft.fftshift(np.fft.fft(seg * np.hanning(n))))
    spec_db = 20*np.log10(spec + 1e-12)
    freqs = np.linspace(-fs/2, fs/2, n)
    band = (freqs > 10e3) & (freqs < 30e3)
    pk = np.argmax(spec_db[band])
    return freqs[band][pk]

def main():
    sdr = SDRplayAPI()
    sdr.select_device(0)
    sdr.set_frequency(88e6)
    sdr.set_gain(40)

    for rate in [2.0e6, 2.4e6, 4.0e6, 6.0e6]:
        try:
            sdr.set_sample_rate(rate)
            iq = sdr.capture(2.0)
            audio = np.diff(np.unwrap(np.angle(iq)))
            f_pilot = find_pilot(audio, rate)
            fs_real = rate * 19e3 / f_pilot
            print(f"设置 {rate/1e6:.1f}M: 导频显示 {f_pilot/1e3:6.2f}kHz "
                  f"=> 实际采样率 {fs_real/1e6:.4f}M  偏差 {abs(fs_real-rate)/rate*100:.2f}%", flush=True)
        except Exception as e:
            print(f"设置 {rate/1e6:.1f}M: 错误 {e}", flush=True)
    sdr.close()

if __name__ == "__main__":
    main()
