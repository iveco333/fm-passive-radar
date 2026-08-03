#!/usr/bin/env python3
"""完整 bwType → 实际采样率 映射测试 (88MHz 台 19kHz 导频反推)
关键: 直接改 bwType 看硬件实际采样率, 证明采样率由 bwType/硬件档位决定"""
import sys, os
import numpy as np
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from sdrplay_api import SDRplayAPI, BW_0_200, BW_0_300, BW_0_600, BW_1_536, BW_5_000, BW_6_000, BW_7_000, BW_8_000

def find_pilot(audio, fs_assumed):
    seg = audio - np.mean(audio)
    n = len(seg)
    spec = np.abs(np.fft.fftshift(np.fft.fft(seg * np.hanning(n))))
    spec_db = 20*np.log10(spec + 1e-12)
    freqs = np.linspace(-fs_assumed/2, fs_assumed/2, n)
    band = (freqs > 12e3) & (freqs < 25e3)
    if not band.any():
        return None
    pk = np.argmax(spec_db[band])
    return freqs[band][pk], spec_db[band][pk] - np.median(spec_db)

def main():
    sdr = SDRplayAPI()
    sdr.select_device(0)
    sdr.set_frequency(88e6)
    sdr.set_gain(40)

    bw_list = [
        ("BW_0_200",  BW_0_200, 0.25e6),
        ("BW_0_300",  BW_0_300, 0.375e6),
        ("BW_0_600",  BW_0_600, 0.75e6),
        ("BW_1_536",  BW_1_536, 2.0e6),
        ("BW_5_000",  BW_5_000, 5.0e6),
        ("BW_6_000",  BW_6_000, 6.0e6),
        ("BW_7_000",  BW_7_000, 7.0e6),
        ("BW_8_000",  BW_8_000, 8.0e6),
    ]
    print(f"{'bwType':<10} {'假设fs':>10} {'导频显示':>10} {'实际采样率':>12}  判定")
    print("-" * 70)
    for name, bw, fs_guess in bw_list:
        try:
            sdr.set_sample_rate(fs_guess)   # 内部按 bwType 映射 (假设)
            sdr.ch.tunerParams.bwType = bw  # 直接强制指定 bwType
            iq = sdr.capture(1.5)
            audio = np.diff(np.unwrap(np.angle(iq)))
            audio = audio - np.mean(audio)
            res = find_pilot(audio, fs_guess)
            if res is None:
                print(f"{name:<10} {fs_guess/1e6:>9.3f}M  无导频")
                continue
            f_disp, over = res
            fs_real = fs_guess * 19e3 / f_disp
            ok = "✓" if abs(fs_real - fs_guess) < 0.05e6 else "← 不一致!"
            print(f"{name:<10} {fs_guess/1e6:>9.3f}M {f_disp/1e3:>8.2f}k {fs_real/1e6:>10.4f}M  {ok}", flush=True)
        except Exception as e:
            print(f"{name:<10} 错误: {e}", flush=True)
    sdr.close()

if __name__ == "__main__":
    main()
