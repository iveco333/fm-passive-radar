#!/usr/bin/env python3
"""UHF 对讲机监听器: 能量突增检测 + FM 语音解调
用法: python listen_uhf.py [频率MHz] [秒数]
默认: 409.750 MHz (公众对讲机 CH1) 30 秒
"""
import sys, os, time
import numpy as np
import scipy.signal as sig
from scipy.io import wavfile
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from sdrplay_api import SDRplayAPI

FS_SET = 0.3e6      # bwType BW_0_300
FS = 0.3668e6         # 实测 BW_0_300 实际采样率
GAIN = 40

def main():
    freq = float(sys.argv[1]) * 1e6 if len(sys.argv) > 1 else 409.750e6
    duration = float(sys.argv[2]) if len(sys.argv) > 2 else 30.0

    sdr = SDRplayAPI()
    sdr.select_device(0)
    sdr.set_sample_rate(FS_SET)
    sdr.set_frequency(freq)
    sdr.set_gain(GAIN)
    print(f"监听 {freq/1e6:.3f} MHz, {duration:.0f}s (增益 {GAIN}dB)", flush=True)

    # 分块采集, 每块 100ms, 检测能量突增
    chunk = 0.1
    n_chunks = int(duration / chunk)
    levels = []
    burst_start = None
    bursts = []

    iq_all = []
    t0 = time.time()
    for ci in range(n_chunks):
        iq = sdr.capture(chunk)
        mag = np.abs(iq)
        lvl = 20*np.log10(np.median(mag) + 1e-12)
        levels.append(lvl)
        iq_all.append(iq)
        # 突发检测: 比前 20 块中位高 6dB
        if len(levels) >= 10:
            base = np.median(levels[-20:])
            if lvl > base + 6 and burst_start is None:
                burst_start = ci
                print(f"  [{time.time()-t0:5.1f}s] 🔥 信号出现! +{lvl-base:.1f}dB", flush=True)
            if lvl <= base + 6 and burst_start is not None:
                bursts.append((burst_start, ci))
                print(f"  [{time.time()-t0:5.1f}s] 信号结束 (持续 {(ci-burst_start)*chunk:.1f}s)", flush=True)
                burst_start = None
        if (ci + 1) % 50 == 0:
            print(f"  [{time.time()-t0:5.1f}s] 电平 {lvl:.0f}dB", flush=True)

    if burst_start is not None:
        bursts.append((burst_start, n_chunks))
    print(f"\n完成. 捕获 {len(bursts)} 段突发", flush=True)

    # 保存 + 解调第一段突发
    if bursts:
        b0, b1 = bursts[0]
        print(f"突发起始 {b0*chunk:.1f}s, 解调语音...", flush=True)
        iq_burst = np.concatenate(iq_all[b0:b1+1])
        audio = np.diff(np.unwrap(np.angle(iq_burst)))
        audio = audio - np.mean(audio)
        # 3kHz 低通 (NFM 语音)
        bb, aa = sig.butter(5, 3000/(FS/2), 'low')
        a_f = sig.filtfilt(bb, aa, audio)
        # 重采样 44100
        rn = int(len(a_f) * 44100 / FS)
        a44 = sig.resample(a_f, rn)
        a44 = a44 / (np.max(np.abs(a44)) + 1e-9)
        out = os.path.join(os.path.dirname(os.path.abspath(__file__)), "uhf_burst.wav")
        wavfile.write(out, 44100, (a44*32767).astype(np.int16))
        print(f"已保存 {out} ({len(a44)/44100:.1f}s)", flush=True)
    else:
        print("没抓到任何突发 (对讲机静默 = 正常)", flush=True)
    sdr.close()

if __name__ == "__main__":
    main()
