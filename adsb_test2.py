"""ADS-B 脉冲检测 v2: 更精细的脉冲统计
"""
import SoapySDR, numpy as np, time

SAMPLE_RATE = 2000000
FREQ = 1090e6

sdr = SoapySDR.Device('driver=sdrplay')
try:
    sdr.setGainMode(SoapySDR.SOAPY_SDR_RX, 0, False)
except Exception:
    pass
sdr.setSampleRate(SoapySDR.SOAPY_SDR_RX, 0, SAMPLE_RATE)
sdr.setFrequency(SoapySDR.SOAPY_SDR_RX, 0, FREQ)
try:
    sdr.setGain(SoapySDR.SOAPY_SDR_RX, 0, 42)
except Exception:
    pass
rx = sdr.setupStream(SoapySDR.SOAPY_SDR_RX, SoapySDR.SOAPY_SDR_CF32)
sdr.activateStream(rx)
time.sleep(1)

buf = np.empty(262144, dtype=np.complex64)
pulse_counts = []
peak_dbfs = []
total_pulses = 0

for i in range(30):
    r = sdr.readStream(rx, [buf], 262144)
    if r.ret <= 0:
        continue
    mag = np.abs(buf[:r.ret])
    # 用能量中位数做底噪估计(更稳)
    noise = np.median(mag)
    thr = noise * 4.0  # 12dB 以上
    n_pulse = int(np.sum(mag > thr))
    pk = 10*np.log10(mag.max() + 1e-12)
    pulse_counts.append(n_pulse)
    peak_dbfs.append(pk)
    total_pulses += n_pulse
    if n_pulse > 50:
        print(f"chunk {i}: peak {pk:.1f} dBFS, 脉冲样本 {n_pulse}  <-- 有脉冲!")

sdr.deactivateStream(rx)
sdr.closeStream(rx)

print(f"\n总脉冲样本: {total_pulses}")
print(f"峰值范围: {min(peak_dbfs):.1f} ~ {max(peak_dbfs):.1f} dBFS")
if total_pulses > 500:
    print("结论: 检测到大量 ADS-B 脉冲, 1090 MHz 有飞机信号!")
elif total_pulses > 0:
    print("结论: 有零星脉冲, 信号较弱")
else:
    print("结论: 未检测到脉冲 (可能只是强干扰/镜像)")
