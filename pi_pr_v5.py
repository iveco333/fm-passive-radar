#!/usr/bin/env python3
"""
Pi FM Passive Radar v5 — 频域DPI + Batch CAF + 保守CLEAN
解决v2/v3 LMS逐点循环过慢问题，避免v4假象峰值
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
    out_png = sys.argv[2] if len(sys.argv) > 2 else '/tmp/pr_v5_result.png'
    fc = float(sys.argv[3]) if len(sys.argv) > 3 else 91.6e6
    
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
    
    # Split: 10% ref, 90% surv (v5: longer ref for better correlation)
    n = len(iq)
    split = int(n * 0.1)
    ref = iq[:split].copy()
    surv = iq[split:].copy()
    print(f"  Ref: {len(ref)/FS:.2f}s, Surv: {len(surv)/FS:.2f}s")
    
    # === 频域 DPI (替代逐点LMS) ===
    # 用参考信号的频谱来抑制监视通道中的直达波
    print(f"[{time.strftime('%H:%M:%S')}] Frequency-domain DPI...")
    
    # 分段处理，每段用参考信号做频域相减
    seg_len = len(ref)
    n_seg = len(surv) // seg_len
    surv_clean = np.zeros(n_seg * seg_len, dtype=np.complex64)
    
    for i in range(n_seg):
        s = surv[i*seg_len:(i+1)*seg_len]
        S = fft(s)
        R = fft(ref)
        # 频域相减：抑制与参考信号强相关的分量
        corr = np.sum(S * np.conj(R)) / (np.sum(np.abs(R)**2) + 1e-10)
        S_clean = S - corr * R * 0.95  # 0.95 = 保守抑制系数
        surv_clean[i*seg_len:(i+1)*seg_len] = ifft(S_clean)
    
    # 只保留处理后的部分
    surv = surv_clean
    print(f"  DPI residual={np.mean(np.abs(surv)):.4f}")
    
    # Normalize
    surv = surv / (np.sqrt(np.mean(np.abs(surv)**2)) + 1e-10)
    
    # === Batch CAF ===
    BLOCK = 2048
    nb = min(len(surv)//BLOCK, 512)
    surv = surv[:nb*BLOCK]
    rf = np.tile(ref, (nb*BLOCK // len(ref)) + 2)[:nb*BLOCK]
    MAX_DELAY = int(30000/(3e8/FS))  # 30km
    
    print(f"[{time.strftime('%H:%M:%S')}] Batch CAF: {nb} blocks x {BLOCK}")
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
    
    # === 保守CLEAN ===
    print(f"[{time.strftime('%H:%M:%S')}] CLEAN...")
    caf_amp = np.abs(caf).copy()
    caf_amp[nb//2-2:nb//2+3, :] = 0  # 更宽的零多普勒抑制
    peaks = []
    for _ in range(15):  # 减少迭代次数，避免假象
        idx = np.argmax(caf_amp)
        di, ri = np.unravel_index(idx, caf_amp.shape)
        pv = caf_amp[di, ri]
        noise = np.median(caf_amp)
        snr = 20*np.log10(pv/(noise+1e-10))
        if snr < 5:  # 提高SNR阈值
            break
        peaks.append((dly[ri], dop[di], snr))
        # 更宽的Gaussian lobe相减
        dd = (np.arange(nb)[:,np.newaxis] - di) / 4
        rr = (np.arange(MAX_DELAY)[np.newaxis,:] - ri) / 3
        caf_amp -= pv * np.exp(-(dd**2 + rr**2))
    
    print(f"\n=== Pi PR v5 Detections ({fc/1e6:.1f} MHz) ===")
    air = [(r,d,s) for r,d,s in peaks if abs(d) < 200 and r > 1]
    other = [(r,d,s) for r,d,s in peaks if abs(d) >= 200 or r <= 1]
    
    print(f"Aircraft range ({len(air)}):")
    for r,d,s in sorted(air, key=lambda x:-x[2])[:10]:
        print(f"  {r:5.1f}km  {d:+.0f}Hz  SNR~{s:.0f}dB")
    
    if other:
        print(f"Other ({len(other)}):")
        for r,d,s in sorted(other, key=lambda x:-x[2])[:5]:
            print(f"  {r:5.1f}km  {d:+.0f}Hz  SNR~{s:.0f}dB")
    
    # Plot
    caf_db = 20 * np.log10(np.abs(caf) + 1e-10)
    caf_db -= np.max(caf_db)
    caf_db = np.clip(caf_db, -35, 0)
    
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(14, 6))
    extent = [dly[0], dly[-1], dop[0], dop[-1]]
    im = ax1.imshow(caf_db, aspect='auto', origin='lower', extent=extent, 
                    cmap='inferno', vmin=-30, vmax=0)
    ax1.set_xlabel('Range (km)'); ax1.set_ylabel('Doppler (Hz)')
    ax1.set_title(f'FM PR v5 ({fc/1e6:.1f} MHz)')
    plt.colorbar(im, ax=ax1, label='dB')
    
    if peaks:
        rs = [p[0] for p in peaks]
        ds = [p[1] for p in peaks]
        ax1.scatter(rs, ds, c='lime', s=40, marker='o', 
                   edgecolors='white', linewidths=0.5)
    
    ax2.plot(dly, caf_db[nb//2])
    ax2.set_xlabel('Range (km)'); ax2.set_ylabel('dB')
    ax2.set_title('Zero-Doppler Cut')
    ax2.grid(alpha=0.3)
    ax2.set_ylim(-45, 2)
    
    plt.tight_layout()
    plt.savefig(out_png, dpi=100)
    print(f"\nSaved: {out_png}")
    print(f"[{time.strftime('%H:%M:%S')}] Done!")

if __name__ == '__main__':
    main()
