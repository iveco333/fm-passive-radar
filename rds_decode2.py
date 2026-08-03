#!/usr/bin/env python3
"""RDS 解码器 v2: 导频相干解调 + 批量 CRC + 全相位扫描 + 0A 组 PS 解析"""
import sys, os
import numpy as np
import scipy.signal as sig
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from sdrplay_api import SDRplayAPI

FREQ = 88e6
FS = 2.375e6
DURATION = 20.0
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

    # 19kHz 导频 → 3 倍频 57kHz 相干参考
    b19, a19 = sig.butter(4, [18.5e3/(FS/2), 19.5e3/(FS/2)], 'band')
    p19 = sig.filtfilt(b19, a19, audio)
    phi19 = np.unwrap(np.angle(sig.hilbert(p19)))
    ref57 = np.exp(1j * 3 * phi19)

    # 57kHz 带通 (收窄到 ±1.5kHz 提 SNR)
    b57, a57 = sig.butter(4, [55.5e3/(FS/2), 58.5e3/(FS/2)], 'band')
    s57 = sig.filtfilt(b57, a57, audio)

    # 相干下变频 + 低通
    bb, aa = sig.butter(5, 1500/(FS/2), 'low')
    base = sig.filtfilt(bb, aa, s57 * ref57.conj())

    # 位定时: 全相位扫描, 批量 CRC 计数
    n_bits = len(base) // SPS
    bits_soft = np.real(base)
    best = []
    for ph in range(0, SPS, 8):
        seq = (bits_soft[ph::SPS] > 0).astype(np.uint8)
        n_blocks = len(seq) // 26
        if n_blocks < 4:
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
            cnt = int(mask.sum())
            if cnt:
                for blk_idx in np.nonzero(mask)[0]:
                    best.append((ph, blk_idx, name, pos, int(data_int[blk_idx]), int(check_int[blk_idx])))
    print(f"有效块总数: {len(best)}", flush=True)
    if not best:
        print("无有效 RDS 块")
        sdr.close()
        return

    # 用块最多的相位
    from collections import Counter
    ph_counts = Counter(b[0] for b in best)
    ph_best, cnt = ph_counts.most_common(1)[0]
    print(f"最优相位 {ph_best} ({cnt} 块)", flush=True)
    blocks = [b for b in best if b[0] == ph_best]

    # 组解析
    groups = {}
    for ph, blk_idx, name, pos, data, check in blocks:
        grp = blk_idx // 4
        groups.setdefault(grp, {})[pos] = (name, data)

    pi = None
    ps = {}
    pty = set()
    for grp, blks in sorted(groups.items()):
        if 0 in blks:  # A 块 = PI
            pi = blks[0][1] & 0xFFFF
        if 1 in blks:
            bdata = blks[1][1]
            gt = (bdata >> 12) & 0xF
            addr = bdata & 0x3
            if gt == 0:  # 0A 组
                if 2 in blks:
                    d = blks[2][1]
                    ps[addr*2] = (d >> 8) & 0xFF
                    ps[addr*2+1] = d & 0xFF
                if 3 in blks:
                    d = blks[3][1]
                    ps[addr*2+2] = (d >> 8) & 0xFF
                    ps[addr*2+3] = d & 0xFF
            ptys.add((bdata >> 5) & 0x1F)

    print(f"\nPI 码: {pi:04X}" if pi is not None else "\nPI: 未收到")
    if ptys:
        pty_names = {0:"无",1:"新闻",2:"当前事件",3:"信息",4:"体育",5:"教育",6:"戏剧",7:"文化",
                     8:"科学",9:"杂谈",10:"流行",11:"摇滚",12:"轻松",13:"轻古典",14:"古典",15:"其他",
                     16:"天气",17:"财经",18:"儿童",19:"社会",20:"宗教",21:"电话点播",22:"旅行",23:"休闲",
                     24:"爵士",25:"乡村",26:"民族",27:"怀旧",28:"民间",29:"纪实",30:"警报",31:"未定义"}
        print(f"PTY: {[pty_names.get(p, p) for p in ptys]}")
    ps_str = ''.join(chr(ps[i]) for i in sorted(ps) if 0x20 <= ps[i] <= 0x7E)
    print(f"电台名 (PS): '{ps_str}'" if ps_str else "电台名: 未收全 (需更多 0A 组)")
    print(f"0A 组数: {len([g for g,b in groups.items() if 1 in b and ((b[1][1]>>12)&0xF)==0])}")
    sdr.close()

if __name__ == "__main__":
    main()
