"""ADS-B 脉冲检测 @ 1MHz 采样 (供电友好版)
"""
import SoapySDR, numpy as np, time

SAMPLE_RATE = 1000000
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
total_pulses = 0
peaks = []
for i in range(30):
    r = sdr.readStream(rx, [buf], 262144)
    if r.ret <= 0:
        continue
    mag = np.abs(buf[:r.ret])
    noise = np.median(mag)
    thr = noise * 4.0
    n_pulse = int(np.sum(mag > thr))
    total_pulses += n_pulse
    pk = 10*np.log10(mag.max() + 1e-12)
    peaks.append(pk)
    if n_pulse > 50:
        print(f"chunk {i}: peak {pk:.1f} dBFS, 脉冲样本 {n_pulse}  <-- 有脉冲!")

try:
    sdr.deactivateStream(rx)
    sdr.closeStream(rx)
except Exception:
    pass

print(f"\n总脉冲样本: {total_pulses}")
print(f"峰值范围: {min(peaks):.1f} ~ {max(peaks):.1f} dBFS")
if total_pulses > 500:
    print("结论: 检测到大量 ADS-B 脉冲!")
elif total_pulses > 0:
    print("结论: 有零星脉冲, 信号较弱")
else:
    print("结论: 未检测到脉冲")
