#!/usr/bin/env python3
"""
Pi FM Passive Radar v2 — 移植 Windows RSP1 成功方案
LMS DPI + Batch CAF + CLEAN
"""
import sys, os, time, numpy as np
sys.path.insert(0, '/tmp')
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from scipy.fft import fft, ifft, fftfreq
from scipy import signal as sp_signal

FS = 2.0e6

def main():
    filename = sys.argv[1] if len(sys.argv) > 1 else '/tmp/fm_iq.dat'
    out_png = sys.argv[2] if len(sys.argv) > 2 else '/tmp/pr_v2_result.png'
    fc = float(sys.argv[3]) if len(sys.argv) > 3 else 88e6
    
    print(f"[{time.strftime('%H:%M:%S')}] Loading: {filename}")
    raw = np.fromfile(filename, dtype=np.uint8)
    iq = (raw.astype(np.float32) - 127.5) / 127.5
    iq = iq[0::2] + 1j * iq[1::2]
    print(f"  {len(iq)} samples ({len(iq)/FS:.1f}s)")
    
    # DC block
    def dc_block(x, blk=1024):
        o = x.copy()
        for i in range(0, len(x), blk):
            b = o[i:i+blk]; o[i:i+blk] = b - np.mean(b)
        return o
    iq = dc_block(iq)
    
    # 19kHz notch (FM stereo pilot)
    b19, a19 = sp_signal.iirnotch(19000/(FS/2), 30, FS)
    iq = sp_signal.filtfilt(b19, a19, iq)
    
    # Low-pass 100kHz
    sos = sp_signal.butter(5, 100e3, 'low', fs=FS, output='sos')
    iq = sp_signal.sosfilt(sos, iq)
    
    # Split: 30% ref, 70% surv
    n = len(iq)
    split = int(n * 0.3)
    ref = iq[:split].copy()
    surv = iq[split:].copy()
    
    # LMS DPI canceller
    M = 48
    mu = 0.008
    w = np.zeros(M, dtype=np.complex64)
    ns = len(surv)
    rp = np.tile(ref, (ns // len(ref)) + 2)[:ns + M]
    for i in range(0, ns, 4096):
        chunk = min(4096, ns - i)
        for j in range(chunk):
            x = rp[i+j:i+j+M]
            e = surv[i+j] - np.dot(w, x)
            w += mu * e * np.conj(x)
            surv[i+j] = e
    print(f"  LMS DPI: residual={np.mean(np.abs(surv)):.4f}")
    
    # Normalize
    surv = surv / (np.sqrt(np.mean(np.abs(surv)**2)) + 1e-10)
    
    # Batch CAF
    BLOCK = 1024  # half of RSP1 version for Pi
    nb = min(len(surv)//BLOCK, 256)  # 256 blocks x 1024 = 262k samples
    surv = surv[:nb*BLOCK]
    rf = ref[:min(len(ref), nb*BLOCK)]
    MAX_DELAY = int(30000/(3e8/FS))  # 30km
    
    print(f"  Batch CAF: {nb} blocks x {BLOCK}")
    corr = np.zeros((MAX_DELAY, nb), dtype=np.complex64)
    for i in range(nb):
        s = surv[i*BLOCK:(i+1)*BLOCK]
        r = rf[i*BLOCK:(i+1)*BLOCK]
        S = fft(s, BLOCK*2)
        R = fft(r, BLOCK*2)
        cc = ifft(S * np.conj(R))
        nt = min(MAX_DELAY, len(cc))
        corr[:nt, i] = cc[:nt]
    
    caf = np.zeros((nb, MAX_DELAY), dtype=np.float32)
    for d in range(MAX_DELAY):
        caf[:, d] = np.abs(fft(corr[d, :], nb))
    caf = np.fft.fftshift(caf, 0)
    dop = np.fft.fftshift(fftfreq(nb, BLOCK/FS))
    dly = np.arange(MAX_DELAY) * (3e8/FS) / 1000
    
    # CLEAN
    caf_amp = np.abs(caf).copy()
    caf_amp[nb//2-1:nb//2+2, :] = 0  # remove zero-Doppler
    peaks = []
    for _ in range(20):
        idx = np.argmax(caf_amp)
        di, ri = np.unravel_index(idx, caf_amp.shape)
        pv = caf_amp[di, ri]
        noise = np.median(caf_amp)
        snr = 20*np.log10(pv/(noise+1e-10))
        if snr < 3:
            break
        peaks.append((dly[ri], dop[di], snr))
        # Subtract Gaussian lobe
        dd = (np.arange(nb)[:,np.newaxis] - di) / 3
        rr = (np.arange(MAX_DELAY)[np.newaxis,:] - ri) / 2
        caf_amp -= pv * np.exp(-(dd**2 + rr**2))
    
    print(f"\n=== Pi Passive Radar v2 Detections ({fc/1e6:.0f} MHz) ===")
    air = [(r,d,s) for r,d,s in peaks if abs(d) < 150 and r > 1]
    other = [(r,d,s) for r,d,s in peaks if abs(d) >= 150 or r <= 1]
    
    print(f"Aircraft range ({len(air)}):")
    for r,d,s in sorted(air, key=lambda x:-x[2])[:10]:
        print(f"  {r:5.1f}km  {d:+.0f}Hz  SNR~{s:.0f}dB")
    
    # Plot
    caf_db = 20 * np.log10(np.abs(caf) + 1e-10)
    caf_db -= np.max(caf_db)
    caf_db = np.clip(caf_db, -30, 0)
    
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(14, 6))
    extent = [dly[0], dly[-1], dop[0], dop[-1]]
    im = ax1.imshow(caf_db, aspect='auto', origin='lower', extent=extent, cmap='inferno', vmin=-25, vmax=0)
    ax1.set_xlabel('Range (km)'); ax1.set_ylabel('Doppler (Hz)')
    ax1.set_title(f'FM PR v2 ({fc/1e6:.0f} MHz)')
    plt.colorbar(im, ax=ax1, label='dB')
    
    if peaks:
        rs = [p[0] for p in peaks]
        ds = [p[1] for p in peaks]
        ax1.scatter(rs, ds, c='lime', s=30, marker='o', edgecolors='white', linewidths=0.5)
    
    ax2.plot(dly, caf_db[nb//2])
    ax2.set_xlabel('Range (km)'); ax2.set_ylabel('dB')
    ax2.set_title('Zero-Doppler Cut')
    ax2.grid(alpha=0.3)
    ax2.set_ylim(-40, 2)
    
    plt.tight_layout()
    plt.savefig(out_png, dpi=100)
    print(f"\nSaved: {out_png}")

if __name__ == '__main__':
    main()
