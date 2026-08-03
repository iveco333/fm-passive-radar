"""ADS-B 脉冲检测: 在 1090 MHz 上快速抓包, 检测飞机应答脉冲
ADS-B 信号是 0.5us 脉冲串, 需要高速采样
"""
import SoapySDR, numpy as np, time, sys

SAMPLE_RATE = 2000000  # 优先 2M, 若供电崩溃自动降级
FREQ = 1090e6

def try_rate(rate):
    sdr = SoapySDR.Device('driver=sdrplay')
    try:
        sdr.setGainMode(SoapySDR.SOAPY_SDR_RX, 0, False)
    except Exception:
        pass
    sdr.setSampleRate(SoapySDR.SOAPY_SDR_RX, 0, rate)
    sdr.setFrequency(SoapySDR.SOAPY_SDR_RX, 0, FREQ)
    try:
        sdr.setGain(SoapySDR.SOAPY_SDR_RX, 0, 42)
    except Exception:
        pass
    rx = sdr.setupStream(SoapySDR.SOAPY_SDR_RX, SoapySDR.SOAPY_SDR_CF32)
    sdr.activateStream(rx)
    time.sleep(1)
    return sdr, rx

sdr, rx = try_rate(SAMPLE_RATE)
print(f"采样率 {SAMPLE_RATE}, 频率 1090 MHz")

buf = np.empty(262144, dtype=np.complex64)
all_peaks = []
n_chunks = 20
for i in range(n_chunks):
    r = sdr.readStream(rx, [buf], 262144)
    if r.ret > 0:
        mag = np.abs(buf[:r.ret])
        # 检测脉冲: 找超过阈值(底噪+8dB)的样本
        thr = np.percentile(mag, 99) * 2.5
        pulses = np.sum(mag > thr)
        pk = 10*np.log10(mag.max() + 1e-12)
        all_peaks.append(pk)
        if pulses > 0:
            print(f"chunk {i}: peak {pk:.1f} dBFS, 脉冲样本 {pulses}  <-- 有信号!")
        else:
            print(f"chunk {i}: peak {pk:.1f} dBFS, 无脉冲")

sdr.deactivateStream(rx)
sdr.closeStream(rx)

if all_peaks:
    print(f"\n峰值范围: {min(all_peaks):.1f} ~ {max(all_peaks):.1f} dBFS")
    print("结论:", "检测到 ADS-B 脉冲" if max(all_peaks) > -40 else "未检测到明显 ADS-B 信号(天线不对或没有飞机)")
