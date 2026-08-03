"""天线测试: 扫描 137MHz 附近频谱, 检查底噪和信号
用法: python3 antenna_test.py [起始MHz] [结束MHz]
"""
import SoapySDR, numpy as np, sys, time

start_mhz = float(sys.argv[1]) if len(sys.argv) > 1 else 136.0
stop_mhz = float(sys.argv[2]) if len(sys.argv) > 2 else 138.5
SAMPLE_RATE = 250000

sdr = SoapySDR.Device('driver=sdrplay')
try:
    sdr.setGainMode(SoapySDR.SOAPY_SDR_RX, 0, False)
except Exception:
    pass
sdr.setSampleRate(SoapySDR.SOAPY_SDR_RX, 0, SAMPLE_RATE)
try:
    sdr.setGain(SoapySDR.SOAPY_SDR_RX, 0, 42)
except Exception:
    pass

rx = sdr.setupStream(SoapySDR.SOAPY_SDR_RX, SoapySDR.SOAPY_SDR_CF32)
sdr.activateStream(rx)
time.sleep(1)

# 逐 200kHz 步进扫描 (RSP1 带宽 250k, 实际可用 ~200k)
freqs = []
powers = []
peaks = []
f = start_mhz
while f <= stop_mhz:
    sdr.setFrequency(SoapySDR.SOAPY_SDR_RX, 0, f * 1e6)
    time.sleep(0.15)
    buf = np.empty(65536, dtype=np.complex64)
    got = 0
    for i in range(3):
        r = sdr.readStream(rx, [buf], 65536)
        if r.ret > 0:
            got = r.ret
            break
    if got > 0:
        sig = np.abs(buf[:got])**2
        power_db = 10*np.log10(sig.mean() + 1e-12)
        peak_db = 10*np.log10(sig.max() + 1e-12)
        freqs.append(f)
        powers.append(power_db)
        peaks.append(peak_db)
        bar = '#' * max(0, int((power_db + 130) / 2))
        print(f"{f:7.2f} MHz  avg {power_db:7.1f} dBFS  peak {peak_db:7.1f} dBFS  {bar}")
    f += 0.2

sdr.deactivateStream(rx)
sdr.closeStream(rx)

# 找最强点
if powers:
    idx = int(np.argmax(powers))
    print(f"\n最强信号: {freqs[idx]:.2f} MHz (avg {powers[idx]:.1f} dBFS)")
    # 找出比底噪高 5dB 以上的信号
    noise = np.percentile(powers, 25)
    print(f"底噪水平: {noise:.1f} dBFS")
    for i in range(len(freqs)):
        if powers[i] - noise > 5:
            print(f"  疑似信号: {freqs[i]:.2f} MHz (+{powers[i]-noise:.1f} dB)")
