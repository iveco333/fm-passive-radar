"""真实 SNR 分析: 从保存的 IQ 重算 CAF, 输出绝对电平与峰-噪比
用法: python snr_real.py <data_file> <ref_s> <surv_s>
"""
import sys, os
import numpy as np
from scipy import signal as sp_signal

FS = 2.375e6

def load_iq(path):
    raw = np.fromfile(path, dtype=np.uint8)
    iq = (raw.astype(np.float32) - 127.5) / 127.5
    iq = iq[0::2] + 1j * iq[1::2]
    return iq

def preprocess(iq):
    def dc_block(x, blk=1024):
        o = x.copy()
        for i in range(0, len(x), blk):
            b = o[i:i+blk]
            o[i:i+blk] = b - np.mean(b)
        return o
    iq = dc_block(iq)
    b19, a19 = sp_signal.iirnotch(19000/(FS/2), 30, FS)
    iq = sp_signal.filtfilt(b19, a19, iq)
    sos = sp_signal.butter(5, 100e3, 'low', fs=FS, output='sos')
    iq = sp_signal.sosfilt(sos, iq)
    return iq

def lms_suppress(ref, surv, M=128, MU=0.002):
    ns = len(surv)
    M_local = min(M, ns // 4)
    rp = np.tile(ref, (ns // len(ref)) + 2)[:ns + M_local]
    w = np.zeros(M_local, dtype=np.complex64)
    out = surv.copy()
    B = 4096
    for i in range(0, ns, B):
        chunk = min(B, ns - i)
        for j in range(chunk):
            x = rp[i+j:i+j+M_local]
            e = out[i+j] - np.dot(w, x)
            w += MU * e * np.conj(x)
            out[i+j] = e
    return out

def caf_peak(ref, surv, MAX_DELAY=800, DOPPLER_RANGE=150, DOPPLER_BINS=61):
    """返回未归一化 CAF 网格 (dB) 和峰值信息"""
    n = min(len(ref), len(surv))
    ref_c = ref[:n].astype(np.complex64)
    surv_out = surv[:n].astype(np.complex64)
    ff = 1
    while ff < n + MAX_DELAY:
        ff <<= 1
    S = np.fft.fft(ref_c, ff)
    dp = np.linspace(-DOPPLER_RANGE, DOPPLER_RANGE, DOPPLER_BINS)
    r = np.zeros((len(dp), MAX_DELAY), dtype=np.complex64)
    for bi, fd in enumerate(dp):
        sf = surv_out * np.exp(-2j * np.pi * fd * np.arange(n) / FS)
        F = np.fft.fft(sf, ff)
        corr = np.fft.ifft(F * np.conj(S))
        r[bi, :MAX_DELAY] = corr[:MAX_DELAY]
    rd = 20 * np.log10(np.maximum(np.abs(r), 1e-10))
    # 未归一化绝对电平 (dBFS)
    peak_abs = rd.max()
    noise_med = np.median(rd)
    # 找峰 (简单: 全局 top 值在 max_delay 限制内, 避开 0-1 bins 直达波区)
    bi, di = np.unravel_index(np.argmax(rd), rd.shape)
    fd_hz = dp[bi]
    r_km = di * (3e8/FS) / 1000
    return peak_abs, noise_med, fd_hz, r_km, rd

if __name__ == '__main__':
    path = sys.argv[1]
    ref_s = float(sys.argv[2])
    surv_s = float(sys.argv[3])
    name = os.path.basename(path)
    print(f"=== {name} (REF={ref_s}s SURV={surv_s}s) ===")
    iq = load_iq(path)
    iq = preprocess(iq)
    n_ref = int(ref_s * FS)
    n_surv = int(surv_s * FS)
    ref = iq[:n_ref].astype(np.complex64)
    surv = iq[int(0.1*FS):int(0.1*FS)+n_surv].astype(np.complex64)
    # 输入信号绝对电平
    in_pow = 10*np.log10(np.mean(np.abs(iq)**2) + 1e-12)
    print(f"输入信号平均功率: {in_pow:.1f} dBFS")
    out = lms_suppress(ref, surv)
    out = out / (np.sqrt(np.mean(np.abs(out)**2)) + 1e-10)
    peak_abs, noise_med, fd, r_km, rd = caf_peak(ref, out)
    print(f"CAF 峰值绝对电平: {peak_abs:.1f} dB (相对归一化后)")
    print(f"CAF 噪声中位数:   {noise_med:.1f} dB")
    print(f"峰-噪比 (peak-med): {peak_abs - noise_med:.1f} dB")
    print(f"峰值位置: 距离 {r_km:.1f} km, 多普勒 {fd:+.0f} Hz")
    # 也输出 top5 峰相对噪声的裕度
    flat = rd.ravel()
    top_idx = np.argsort(flat)[::-1][:5]
    print("Top5 峰相对噪声裕度 (dB):", ", ".join(f"{flat[i]-noise_med:.1f}" for i in top_idx))
    print()
