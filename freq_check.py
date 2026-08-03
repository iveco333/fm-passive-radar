import SoapySDR, numpy as np, time, sys

freq = float(sys.argv[1]) * 1e6 if len(sys.argv) > 1 else 1085e6
SAMPLE_RATE = 2000000

sdr = SoapySDR.Device('driver=sdrplay')
try:
    sdr.setGainMode(SoapySDR.SOAPY_SDR_RX, 0, False)
except Exception:
    pass
sdr.setSampleRate(SoapySDR.SOAPY_SDR_RX, 0, SAMPLE_RATE)
sdr.setFrequency(SoapySDR.SOAPY_SDR_RX, 0, freq)
try:
    sdr.setGain(SoapySDR.SOAPY_SDR_RX, 0, 42)
except Exception:
    pass
rx = sdr.setupStream(SoapySDR.SOAPY_SDR_RX, SoapySDR.SOAPY_SDR_CF32)
sdr.activateStream(rx)
time.sleep(1)
buf = np.empty(262144, dtype=np.complex64)
peaks = []
medians = []
for i in range(10):
    r = sdr.readStream(rx, [buf], 262144)
    if r.ret > 0:
        mag = np.abs(buf[:r.ret])
        peaks.append(10*np.log10(mag.max()+1e-12))
        medians.append(10*np.log10(np.median(mag)+1e-12))
sdr.deactivateStream(rx)
sdr.closeStream(rx)
print(f"{freq/1e6:.0f} MHz peaks:", [f'{p:.1f}' for p in peaks])
print(f"{freq/1e6:.0f} MHz med:", [f'{m:.1f}' for m in medians])
