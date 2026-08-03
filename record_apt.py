"""NOAA APT 信号录制脚本 - 用 RSP1 通过 SoapySDR 录 IQ 到 WAV
用法: python3 record_apt.py <频率MHz> <时长秒> <输出文件>
例: python3 record_apt.py 137.9125 600 /home/iveco/noaa/NOAA19_20260801_1159.wav
"""
import SoapySDR, numpy as np, sys, time, wave

freq_mhz = float(sys.argv[1])
duration = int(sys.argv[2])
outfile = sys.argv[3]

SAMPLE_RATE = 250000  # APT 带宽 34kHz,250k 足够
GAIN = 42

sdr = SoapySDR.Device('driver=sdrplay')
try:
    sdr.setGainMode(SoapySDR.SOAPY_SDR_RX, 0, False)
except Exception:
    pass
sdr.setSampleRate(SoapySDR.SOAPY_SDR_RX, 0, SAMPLE_RATE)
sdr.setFrequency(SoapySDR.SOAPY_SDR_RX, 0, freq_mhz * 1e6)
try:
    sdr.setGain(SoapySDR.SOAPY_SDR_RX, 0, GAIN)
except Exception:
    pass
print(f"频率 {freq_mhz} MHz, 采样率 {SAMPLE_RATE}, 时长 {duration}s, 增益 {GAIN}")

rx = sdr.setupStream(SoapySDR.SOAPY_SDR_RX, SoapySDR.SOAPY_SDR_CF32)
sdr.activateStream(rx)
time.sleep(1)

total = SAMPLE_RATE * duration
chunk = 65536
samples = []
got = 0
t0 = time.time()
errs = 0
while got < total and time.time() - t0 < duration + 15:
    buf = np.empty(chunk, dtype=np.complex64)
    r = sdr.readStream(rx, [buf], chunk)
    if r.ret > 0:
        samples.append(buf[:r.ret].copy())
        got += r.ret
    elif r.ret < 0:
        errs += 1

sdr.deactivateStream(rx)
sdr.closeStream(rx)

iq = np.concatenate(samples) if samples else np.array([], dtype=np.complex64)
print(f"采集 {got} samples ({got/SAMPLE_RATE:.1f}s), 错误 {errs}")

# 保存为 int16 交错 WAV (I/Q), satdump 可读
iq16 = (iq / (np.abs(iq).max() + 1e-9) * 32000).astype(np.int16)
iq_int = np.empty(iq16.size * 2, dtype=np.int16)
iq_int[0::2] = iq16.real
iq_int[1::2] = iq16.imag

with wave.open(outfile, 'wb') as w:
    w.setnchannels(2)
    w.setsampwidth(2)
    w.setframerate(SAMPLE_RATE)
    w.writeframes(iq_int.tobytes())
print(f"已保存 {outfile} ({iq_int.size*2} bytes)")
