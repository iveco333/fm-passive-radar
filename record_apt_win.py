#!/usr/bin/env python3
"""Windows NOAA APT 录制 - RSP1 直驱
用法: python record_apt_win.py <频率MHz> <时长秒> <输出wav>
"""
import sys, os, time
import numpy as np
import wave

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from sdrplay_api import SDRplayAPI

freq_mhz = float(sys.argv[1])
duration = int(sys.argv[2])
outfile = sys.argv[3]

FS = 250000  # APT 带宽 34kHz, 250k 足够, 文件也小
GAIN = 30

sdr = SDRplayAPI()
sdr.select_device(0)
sdr.set_frequency(freq_mhz * 1e6)
sdr.set_sample_rate(FS)
sdr.set_gain(GAIN)
print(f"频率 {freq_mhz} MHz, 采样率 {FS}, 时长 {duration}s, 增益 {GAIN}", flush=True)

t0 = time.time()
iq = sdr.capture(duration)
sdr.close()
elapsed = time.time() - t0
print(f"采集 {len(iq)} samples ({elapsed:.0f}s)", flush=True)

# 归一化 + 转 int16 交错 (satdump 可读的 WAV)
mag = np.abs(iq)
scale = np.percentile(mag, 99.9) + 1e-9
iq_norm = iq / scale * 30000
iq_int = np.empty(iq_norm.size * 2, dtype=np.int16)
iq_int[0::2] = iq_norm.real.astype(np.int16)
iq_int[1::2] = iq_norm.imag.astype(np.int16)

with wave.open(outfile, 'wb') as w:
    w.setnchannels(2)
    w.setsampwidth(2)
    w.setframerate(FS)
    w.writeframes(iq_int.tobytes())
print(f"已保存 {outfile} ({os.path.getsize(outfile)/1e6:.0f} MB)", flush=True)
