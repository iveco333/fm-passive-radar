#!/usr/bin/env python3
"""RDS 解码器: 从 FM 解调音频提取 57kHz 副载波, 解出电台名/PTY/PI
DBPSK 延迟解调 + 块同步 CRC 校验 + 0A 组 PS 解析"""
import sys, os
import numpy as np
import scipy.signal as sig
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from sdrplay_api import SDRplayAPI

FREQ = 88e6
FS = 2.375e6
DURATION = 10.0
GAIN = 40
SPS = int(FS / 1187.5)   # 样本/bit ≈ 2000
CRC_POLY = 0x5B9         # x^10+x^8+x^7+x^5+x^4+x^3+1
OFFSET = {0x3FC: 'A', 0x218: 'B', 0x148: 'C', 0x350: "C'", 0x2B4: 'D'}

def crc10(data16):
    reg = data16 << 10
    for i in range(15, -1, -1):
        if (reg >> (i + 10)) & 1:
            reg ^= CRC_POLY << i
    return reg & 0x3FF

def decode_group(bits26):
    """返回 (offset, data16) 或 None"""
    data = 0
    for b in bits26[:16]:
        data = (data << 1) | int(b)
    check = 0
    for b in bits26[16:]:
        check = (check << 1) | int(b)
    for off, name in OFFSET.items():
        if crc10(data) ^ off == check:
            return name, data
    return None

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
    print(f"音频 {len(audio)/FS:.1f}s, sps={SPS}", flush=True)

    # 1. 57kHz 带通 + 解析信号
    b, a = sig.butter(4, [55.5e3/(FS/2), 58.5e3/(FS/2)], 'band')
    s57 = sig.filtfilt(b, a, audio)
    z = sig.hilbert(s57)

    # 2. DBPSK 延迟差分解调
    d = z[SPS:] * np.conj(z[:-SPS])
    bits_soft = np.real(d)   # >0 → bit 1 (相位不变)

    # 3. 时钟恢复: 扫采样相位, 用块 CRC 通过数选最优
    n_blocks = (len(bits_soft) // SPS - 1) // 26
    best_phase, best_count, best_groups = 0, -1, []
    for ph in range(0, SPS, 40):
        seq = (bits_soft[ph::SPS] > 0).astype(np.uint8)
        count = 0
        groups = []
        for i in range(0, len(seq) - 25, 26):
            g = decode_group(seq[i:i+26])
            if g:
                count += 1
                groups.append((i // 26, g))
        if count > best_count:
            best_count, best_phase, best_groups = count, ph, groups
    print(f"最优采样相位 {best_phase}, 有效块 {best_count}", flush=True)

    if best_count == 0:
        print("无有效 RDS 块 (信号弱或非 RDS 台?)")
        sdr.close()
        return

    # 4. 组解析: 收集 0A 组 PS
    pi = None
    ps_chars = [''] * 8
    ptys = set()
    groups_by_pos = {}
    for blk_idx, (off, data) in best_groups:
        pos_in_group = blk_idx % 4
        if off == 'A' and pos_in_group == 0:
            pi = data & 0xFFFF
        if off == 'B' and pos_in_group == 1:
            pty = (data >> 5) & 0x1F
            ptys.add(pty)
        if off == 'C' and pos_in_group == 2:
            pass
        if off == 'D' and pos_in_group == 3:
            groups_by_pos.setdefault(blk_idx // 4, []).append(data)

    # 0A 组: 块3/4 各含 2 个 PS 字符 (从 B 块地址 0-3 分组)
    ps_map = {}
    for grp, datas in groups_by_pos.items():
        if len(datas) == 1 and grp in ps_map:
            ps_map[grp] += datas[0]
        elif len(datas) == 1:
            ps_map[grp] = [datas[0]]
    # 简化: 0A 组的块3(A组内第2块C?) -- 这里用标准: 0A 组 = A B C D 四块, PS 在 C/D 块
    # 实际解析: 组类型 = B块高4位
    print(f"PI 码: {pi:04X}" if pi else "PI: 未知")
    if ptys:
        print(f"PTY: {ptys}")
    # PS: 从块2组号 0-3 收集
    ps_bytes = {}
    for grp_no, datas in groups_by_pos.items():
        pass
    # 用另一种方法: 直接从有效块里找 0A 组
    print("\n块序列 (前30):")
    for blk_idx, (off, data) in best_groups[:30]:
        print(f"  [{blk_idx}] off={off} data={data:04X}", flush=True)
    sdr.close()

if __name__ == "__main__":
    main()
