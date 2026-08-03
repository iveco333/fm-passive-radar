#!/usr/bin/env python3
"""RDS 解码器 v3: 频移校正 + 积分-转储 + 差分 BPSK + 批量 CRC"""
import sys, os
import numpy as np
import scipy.signal as sig
from collections import Counter
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from sdrplay_api import SDRplayAPI

FREQ = 88e6
FS = 2.375e6
DURATION = 45.0
GAIN = 40
SPS = int(FS / 1187.5)   # 2000
CRC_POLY = 0x5B9
OFFSETS = [(0x3FC, 'A', 0), (0x218, 'B', 1), (0x148, 'C', 2), (0x2B4, 'D', 3), (0x350, "C'", 3)]

def crc10_batch(data_int):
    reg = data_int.astype(np.int64) << 10
    for i in range(15, -1, -1):
        bit = (reg >> (i + 10)) & 1
        reg ^= np.where(bit == 1, CRC_POLY << i, 0)
    return reg & 0x3FF

def main():
    sdr = SDRplayAPI()
    sdr.select_device(0)
    sdr.set_sample_rate(1.94e6)
    sdr.set_frequency(FREQ)
    sdr.set_gain(GAIN)
    print(f"调谐 {FREQ/1e6}MHz, 采 {DURATION}s...", flush=True)
    iq = sdr.capture(DURATION)
    audio = np.diff(np.unwrap(np.angle(iq)))
    audio = audio - np.mean(audio)
    print(f"音频 {len(audio)/FS:.1f}s", flush=True)

    # 精确定位 57k 峰
    seg = audio[:int(FS*4)] * np.hanning(int(FS*4))
    spec = np.abs(np.fft.fftshift(np.fft.fft(seg)))
    freqs = np.linspace(-FS/2, FS/2, len(spec))
    band = (freqs > 55e3) & (freqs < 59e3)
    pk = np.argmax(spec[band])
    f57 = freqs[band][pk]
    print(f"57kHz 峰实际位置: {f57/1e3:.3f} kHz (偏移 {f57-57e3:+.0f} Hz)", flush=True)

    # 频移校正到精确 57k
    t = np.arange(len(audio)) / FS
    audio_c = audio * np.exp(-1j * 2*np.pi * (f57 - 57e3) * t)

    # 带通 + 积分-转储
    b, a = sig.butter(4, [55.2e3/(FS/2), 58.8e3/(FS/2)], 'band')
    z = sig.hilbert(sig.filtfilt(b, a, audio_c))
    n_bits = len(z) // SPS
    z_bits = z[:n_bits*SPS].reshape(n_bits, SPS).mean(axis=1)
    # 差分 BPSK: 相邻 bit 相位相同=1, 翻转=0
    d = z_bits[1:] * np.conj(z_bits[:-1])
    bits_soft = np.real(d)
    print(f"bit 数: {len(bits_soft)}", flush=True)

    # 相位扫描 + 批量 CRC
    best = []
    for ph in range(0, SPS, 4):
        seq = (bits_soft[ph::SPS] > 0).astype(np.uint8)
        n_blocks = len(seq) // 26
        if n_blocks < 10:
            continue
        seq2 = seq[:n_blocks*26].reshape(n_blocks, 26)
        data_int = np.zeros(n_blocks, np.int64)
        for k in range(16):
            data_int = (data_int << 1) | seq2[:, k].astype(np.int64)
        check_int = np.zeros(n_blocks, np.int64)
        for k in range(10):
            check_int = (check_int << 1) | seq2[:, 16+k].astype(np.int64)
        crc = crc10_batch(data_int)
        for off, name, pos in OFFSETS:
            mask = (crc ^ off) == check_int
            for blk_idx in np.nonzero(mask)[0]:
                best.append((ph, blk_idx, name, pos, int(data_int[blk_idx])))
    print(f"有效块总数: {len(best)}", flush=True)
    if not best:
        print("无有效 RDS 块")
        sdr.close()
        return

    ph_counts = Counter(b[0] for b in best)
    ph_best, cnt = ph_counts.most_common(1)[0]
    print(f"最优相位 {ph_best} ({cnt} 块)", flush=True)
    blocks = [b for b in best if b[0] == ph_best]

    groups = {}
    for ph, blk_idx, name, pos, data in blocks:
        groups.setdefault(blk_idx // 4, {})[pos] = (name, data)

    pi = None
    ps = {}
    ptys = set()
    n_0a = 0
    for grp, blks in sorted(groups.items()):
        if 0 in blks:
            pi = blks[0][1] & 0xFFFF
        if 1 in blks:
            bdata = blks[1][1]
            gt = (bdata >> 12) & 0xF
            addr = bdata & 0x3
            if gt == 0:
                n_0a += 1
                if 2 in blks:
                    d = blks[2][1]
                    ps[addr*2] = (d >> 8) & 0xFF
                    ps[addr*2+1] = d & 0xFF
                if 3 in blks:
                    d = blks[3][1]
                    ps[addr*2+2] = (d >> 8) & 0xFF
                    ps[addr*2+3] = d & 0xFF
            ptys.add((bdata >> 5) & 0x1F)

    print(f"\nPI: {pi:04X}" if pi is not None else "\nPI: 未收到")
    print(f"PTY: {sorted(ptys)}")
    ps_str = ''.join(chr(ps[i]) for i in sorted(ps) if 0x20 <= ps[i] <= 0x7E)
    print(f"电台名: '{ps_str}'" if ps_str else "电台名: 未收全")
    print(f"0A 组数: {n_0a}, 完整组数: {len(groups)}")
    sdr.close()

if __name__ == "__main__":
    main()
