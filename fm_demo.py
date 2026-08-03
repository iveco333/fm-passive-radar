#!/usr/bin/env python3
"""FM 广播解调 + 19kHz 导频校准 + RDS 副载波检测
88MHz 是西安最强 FM 台, 用来验证接收链路 + 测实际采样率"""
import sys, os
import numpy as np
import scipy.signal as sig
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from sdrplay_api import SDRplayAPI

FREQ = 88e6
FS = 1.94e6  # 假设采样率(实际可能不同, 用导频校准)
DURATION = 3.0
GAIN = 40

def main():
    sdr = SDRplayAPI()
    sdr.select_device(0)
    sdr.set_sample_rate(FS)
    sdr.set_frequency(FREQ)
    sdr.set_gain(GAIN)
    print(f"调谐 {FREQ/1e6}MHz, 采 {DURATION}s...", flush=True)
    iq = sdr.capture(DURATION)
    n = len(iq)
    print(f"实际采样数: {n} (假设 {FS*DURATION:.0f})", flush=True)

    # FM 鉴频
    phase = np.unwrap(np.angle(iq))
    audio = np.diff(phase)
    fs_audio = FS  # 暂用假设采样率

    # 解调后频谱: 找 19k(导频) 38k(立体声) 57k(RDS) 峰
    seg = audio[:int(fs_audio*2)]
    seg = seg - np.mean(seg)
    win = np.hanning(len(seg))
    spec = np.abs(np.fft.fftshift(np.fft.fft(seg * win)))
    spec_db = 20*np.log10(spec + 1e-12)
    freqs = np.linspace(-fs_audio/2, fs_audio/2, len(spec))

    # 正频率范围找峰
    pos = freqs > 0
    f_pos, s_pos = freqs[pos], spec_db[pos]
    # 找 15-25kHz 内最大峰 = 19kHz 导频
    band = (f_pos > 15e3) & (f_pos < 25e3)
    if band.any():
        pk = np.argmax(s_pos[band])
        f_pilot = f_pos[band][pk]
        print(f"19kHz 导频候选: {f_pilot/1e3:.2f} kHz  (+{s_pos[band][pk]-np.median(spec_db):.0f} dB)")
        # 用导频校准实际采样率
        fs_real = fs_audio * 19e3 / f_pilot
        print(f"=> 实际采样率 ≈ {fs_real/1e6:.3f} MSPS")
        # 校准后重算 RDS 峰位置
        f_rds = 57e3 * f_pilot / 19e3
        print(f"=> 预期 RDS 57kHz 副载波在 {f_rds/1e3:.2f} kHz")
    else:
        print("15-25kHz 无峰, 可能没有立体声导频或采样率标定差太多")

    # 通用: 打印正频 0-100kHz 前 8 个峰
    pk_idx = np.argsort(s_pos)[-8:][::-1]
    print("\n0-100kHz 最强峰:")
    for i in sorted(pk_idx, key=lambda j: f_pos[j]):
        print(f"  {f_pos[i]/1e3:7.2f} kHz  (+{s_pos[i]-np.median(spec_db):.0f} dB)", flush=True)

    # 保存解调音频 WAV (44.1kHz 重采样, 可听)
    try:
        from scipy.io import wavfile
        b, a = sig.butter(5, 15000/(fs_audio/2), 'low')
        audio_f = sig.filtfilt(b, a, audio)
        # 重采样到 44100
        resample_n = int(len(audio_f) * 44100 / fs_audio)
        audio_44 = sig.resample(audio_f, resample_n)
        audio_44 = audio_44 / (np.max(np.abs(audio_44)) + 1e-9)
        wavfile.write("fm_88mhz_demo.wav", 44100, (audio_44*32767).astype(np.int16))
        print(f"\n已保存 fm_88mhz_demo.wav ({len(audio_44)/44100:.1f}s)", flush=True)
    except Exception as e:
        print(f"WAV 保存失败: {e}")

    sdr.close()

if __name__ == "__main__":
    main()
