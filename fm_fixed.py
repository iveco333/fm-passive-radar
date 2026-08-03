#!/usr/bin/env python3
"""修正采样率后的 FM 解调: 88MHz 广播 + 导频/RDS 检测 + 可听 WAV"""
import sys, os
import numpy as np
import scipy.signal as sig
from scipy.io import wavfile
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from sdrplay_api import SDRplayAPI

FREQ = 88e6
FS_REAL = 2.375e6   # 实测: BW_1_536 时实际采样率
DURATION = 8.0
GAIN = 40

def main():
    sdr = SDRplayAPI()
    sdr.select_device(0)
    sdr.set_sample_rate(1.94e6)  # bwType 选择 (实际输出 2.375M)
    sdr.set_frequency(FREQ)
    sdr.set_gain(GAIN)
    print(f"调谐 {FREQ/1e6}MHz (实际采样率 {FS_REAL/1e6:.3f}M), 采 {DURATION}s", flush=True)
    iq = sdr.capture(DURATION)
    print(f"样本数 {len(iq)} = {len(iq)/FS_REAL:.1f}s", flush=True)

    # FM 鉴频
    audio = np.diff(np.unwrap(np.angle(iq)))
    audio = audio - np.mean(audio)

    # 解调后频谱: 19k 导频, 38k 立体声, 57k RDS
    seg = audio[:int(FS_REAL*4)]
    seg = seg * np.hanning(len(seg))
    spec = np.abs(np.fft.fftshift(np.fft.fft(seg)))
    spec_db = 20*np.log10(spec + 1e-12)
    freqs = np.linspace(-FS_REAL/2, FS_REAL/2, len(spec))
    pos = freqs > 0
    noise = np.median(spec_db)
    print(f"\n解调后频谱峰 (修正标定):")
    for target, label in [(19e3, "19kHz 立体声导频"), (38e3, "38kHz 副载波"), (57e3, "57kHz RDS"), (76e3, "76kHz 副载波谐波")]:
        band = (freqs > target-500) & (freqs < target+500)
        if band.any():
            pk = np.argmax(spec_db[band])
            print(f"  {label}: {freqs[band][pk]/1e3:6.2f} kHz  (+{spec_db[band][pk]-noise:.0f} dB)", flush=True)

    # 0-80kHz 全峰
    band = (freqs > 1e3) & (freqs < 80e3)
    idx = np.argsort(spec_db[band])[-10:][::-1]
    print("  最强峰:", "  ".join(f"{freqs[band][i]/1e3:.1f}k({spec_db[band][i]-noise:+.0f})"
          for i in sorted(idx, key=lambda j: freqs[band][j])), flush=True)

    # 音频质量: 语音/音乐判断 (过零率)
    zcr = np.mean(np.abs(np.diff(np.sign(audio[::10]))))/2
    print(f"\n过零率(粗): {zcr:.4f} (音乐通常 <0.1, 语音有停顿变化)")

    # 保存可听 WAV (44.1kHz)
    b, a = sig.butter(5, 15000/(FS_REAL/2), 'low')
    audio_f = sig.filtfilt(b, a, audio)
    resample_n = int(len(audio_f) * 44100 / FS_REAL)
    audio_44 = sig.resample(audio_f, resample_n)
    audio_44 = audio_44 / (np.max(np.abs(audio_44)) + 1e-9)
    wavfile.write("fm_88mhz_fixed.wav", 44100, (audio_44*32767).astype(np.int16))
    print(f"\n已保存 fm_88mhz_fixed.wav ({len(audio_44)/44100:.1f}s @44.1kHz)", flush=True)
    sdr.close()

if __name__ == "__main__":
    main()
