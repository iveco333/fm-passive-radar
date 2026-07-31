"""FM PR at 91.6 MHz for TX triangulation."""
import sys, os, numpy as np, time
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from sdrplay_api import SDRplayAPI
from scipy import signal as sp_signal
from scipy.fft import fft, ifft, fftfreq

FS = 1.98e6; FREQ = 91.6e6; GAIN = 20;

with SDRplayAPI() as sdr:
    sdr.select_device(0)
    sdr.set_frequency(FREQ)
    sdr.set_sample_rate(FS)
    sdr.set_gain(GAIN)
    iq = sdr.capture(4.0)

def dc_block(x, blk=1024):
    o = x.copy()
    for i in range(0, len(x), blk):
        b = o[i:i+blk]; o[i:i+blk] = b - np.mean(b)
    return o

iq = dc_block(iq)
b19, a19 = sp_signal.iirnotch(19000/(FS/2), 30, FS)
iq = sp_signal.filtfilt(b19, a19, iq)
sos = sp_signal.butter(5, 100e3, 'low', fs=FS, output='sos')
iq = sp_signal.sosfilt(sos, iq)

n = len(iq); split = int(n * 0.1)
ref = iq[:split].copy(); surv = iq[split:].copy()

M = 64; mu = 0.01; w = np.zeros(M, dtype=np.complex64)
ns = len(surv); rp = np.tile(ref, (ns // len(ref)) + 2)[:ns + M]
for i in range(ns):
    x = rp[i:i+M]; w += mu * (surv[i] - np.dot(w, x)) * np.conj(x); surv[i] -= np.dot(w, x)

surv = surv / np.sqrt(np.mean(np.abs(surv)**2) + 1e-10)

BLOCK = 2048; nb = min(len(surv)//BLOCK, 512); surv = surv[:nb*BLOCK]
rf = ref[:min(len(ref), nb*BLOCK)]
MAX_DELAY = int(45000/(3e8/FS))
corr = np.zeros((MAX_DELAY, nb), dtype=np.complex64)
for i in range(nb):
    s=surv[i*BLOCK:(i+1)*BLOCK]; r=rf[i*BLOCK:(i+1)*BLOCK]
    S=fft(s,BLOCK*2); R=fft(r,BLOCK*2); cc=ifft(S*np.conj(R))
    nt=min(MAX_DELAY,len(cc)); corr[:nt,i]=cc[:nt]

caf=np.zeros((nb,MAX_DELAY),dtype=np.float32)
for d in range(MAX_DELAY): caf[:,d]=np.abs(fft(corr[d,:],nb))
caf=np.fft.fftshift(caf,0)
dop=np.fft.fftshift(fftfreq(nb,BLOCK/FS))
dly=np.arange(MAX_DELAY)*(3e8/FS)/1000

caf_amp = np.abs(caf)
caf_amp[nb//2-1:nb//2+2,:] = 0
peaks = []
for _ in range(20):
    idx = np.argmax(caf_amp); di, ri = np.unravel_index(idx, caf_amp.shape)
    pv = caf_amp[di,ri]; noise = np.median(caf_amp)
    snr = 20*np.log10(pv/(noise+1e-10))
    if snr < 3: break
    peaks.append((dly[ri], dop[di], snr))
    dd = (np.arange(nb)[:,np.newaxis]-di)/3; rr = (np.arange(MAX_DELAY)[np.newaxis,:]-ri)/2
    caf_amp -= pv * np.exp(-(dd**2+rr**2))

print("=== 91.6 MHz PR Detections ===")
for r, d, s in sorted(peaks, key=lambda x: -x[2])[:20]:
    print(f"  {r:5.1f}km  {d:+.0f}Hz  SNR~{s:.0f}dB")
