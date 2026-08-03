#!/usr/bin/env python3
"""RDS 解码器 v4: 带通 57k + hilbert + 积分转储 + 差分 BPSK + 批量 CRC"""
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

def try_phase(z, ph, SPS):
    """在 bit 起点 ph 做积分转储+差分, 返回 bit 序列"""
    n_bits = (len(z) - ph) // SPS
    if n_bits < 100:
        return None
    z_bits = z[ph:ph + n_bits*SPS].reshape(n_bits, SPS).mean(axis=1)
    d = z_bits[1:] * np.conj(z_bits[:-1])
    return (np.real(d) > 0).astype(np.uint8)

def decode_blocks(seq):
    n_blocks = len(seq) // 26
    if n_blocks < 5:
        return []
    seq2 = seq[:n_blocks*26].reshape(n_blocks, 26)
    data_int = np.zeros(n_blocks, np.int64)
    for k in range(16):
        data_int = (data_int << 1) | seq2[:, k].astype(np.int64)
    check_int = np.zeros(n_blocks, np.int64)
    for k in range(10):
        check_int = (check_int << 1) | seq2[:, 16+k].astype(np.int64)
    crc = crc10_batch(data_int)
    out = []
    for off, name, pos in OFFSETS:
        mask = (crc ^ off) == check_int
        for blk_idx in np.nonzero(mask)[0]:
            out.append((blk_idx, name, pos, int(data_int[blk_idx])))
    return out

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

    # 带通 57k ± 2k + hilbert (实部输入)
    b, a = sig.butter(4, [55e3/(FS/2), 59e3/(FS/2)], 'band')
    z = sig.hilbert(sig.filtfilt(b, a, audio))
    print("解析信号就绪", flush=True)

    # 粗扫相位 → 细扫
    best_all = []
    for ph in range(0, SPS, 100):
        seq = try_phase(z, ph, SPS)
        if seq is None:
            continue
        for blk in decode_blocks(seq):
            best_all.append((ph, blk))
    print(f"粗扫有效块: {len(best_all)}", flush=True)
    if best_all:
        ph_counts = Counter(b[0] for b in best_all)
        ph_best, cnt = ph_counts.most_common(1)[0]
        print(f"最优粗相位 {ph_best} ({cnt}块), 细扫 ±100", flush=True)
        fine = []
        for ph in range(max(0, ph_best-100), min(SPS, ph_best+100), 4):
            seq = try_phase(z, ph, SPS)
            if seq is None:
                continue
            for blk in decode_blocks(seq):
                fine.append((ph, blk))
        if len(fine) > len(best_all):
            best_all = fine
            ph_counts = Counter(b[0] for b in best_all)
            ph_best, cnt = ph_counts.most_common(1)[0]
            print(f"细扫后: 相位 {ph_best}, {cnt} 块")

    if not best_all:
        print("无有效 RDS 块")
        sdr.close()
        return

    ph_best = Counter(b[0] for b in best_all).most_common(1)[0][0]
    blocks = [b[1] for b in best_all if b[0] == ph_best]
    print(f"最终: 相位 {ph_best}, 有效块 {len(blocks)}", flush=True)

    groups = {}
    for blk_idx, name, pos, data in blocks:
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
