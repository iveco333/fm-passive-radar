#!/usr/bin/env python3
"""分析 adsb_1090_v2.bin: 脉冲宽度/间隔/幅度分布, 判断真假 ADS-B"""
import sys, os
import numpy as np
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

FS = 2.375e6
iq = np.fromfile(os.path.join(os.path.dirname(os.path.abspath(__file__)), "adsb_1090_v2.bin"), dtype=np.complex64)
print(f"样本: {len(iq)} = {len(iq)/FS:.2f}s", flush=True)

mag = np.abs(iq)
p99 = np.percentile(mag, 99)
thr = p99 * 0.8
above = mag > thr

# 1. 脉冲统计: 找连续 above 段 (脉冲)
pulses = []
start = None
for i in range(len(above)):
    if above[i] and start is None:
        start = i
    elif not above[i] and start is not None:
        pulses.append((start, i - start))
        start = None
if start is not None:
    pulses.append((start, len(above) - start))

widths_us = np.array([w / FS * 1e6 for _, w in pulses])
amps = np.array([np.max(mag[s:s+w]) for s, w in pulses])
print(f"\n脉冲总数: {len(pulses)}")
print(f"宽度分布 (us): min={widths_us.min():.2f} p25={np.percentile(widths_us,25):.2f} "
      f"中位={np.median(widths_us):.2f} p75={np.percentile(widths_us,75):.2f} max={widths_us.max():.2f}")
print(f"宽度 >0.8us 的比例: {np.mean(widths_us > 0.8)*100:.1f}%  (真 ADS-B 数据位 ~1us)")
print(f"幅度分布: 中位={np.median(amps):.3f} p99={np.percentile(amps,99):.3f} max={amps.max():.3f}")
print(f"饱和脉冲 (amp>0.9): {np.mean(amps > 0.9)*100:.2f}%")

# 2. 前导检测更严格: 检查前导后 8us 的数据位是否有脉冲流
bit = int(FS * 1e-6)
# 真前导: 0.5us 处有脉冲, 1us 处无, 1.5us 处无, 2us 处有, 2.5us 处无, 3us 处无, 3.5us 处有
def is_preamble(m, i):
    try:
        return (m[i] > thr and m[i + bit//2] > thr and
                not m[i + bit] and not m[i + bit + bit//2] and
                m[i + 2*bit] > thr and
                not m[i + 2*bit + bit//2] and not m[i + 3*bit] and
                m[i + int(3.5*bit)] > thr)
    except IndexError:
        return False

# 数据位检测: 前导后 8us 起 112 位, 位中心采样
def decode_frame(m, start):
    bits = []
    for bb in range(112):
        s = start + 8*bit + bb*bit
        if s + bit >= len(m):
            return None
        bits.append(1 if np.mean(m[s:s+bit]) > thr else 0)
    return "".join(str(x) for x in bits)

n_pream = 0
n_decode_ok = 0
df_counts = {}
for i in range(200, len(mag) - 400):
    if is_preamble(mag, i):
        n_pream += 1
        hx = decode_frame(mag, i)
        if hx and hx[:5] != "00000":
            # 检查 DF (前 5 bit)
            df = int(hx[:5], 2)
            df_counts[df] = df_counts.get(df, 0) + 1
            n_decode_ok += 1
print(f"\n严格前导检测: {n_pream} 个")
print(f"解码出 112bit 帧: {n_decode_ok} 个")
if df_counts:
    print(f"DF 分布: {dict(sorted(df_counts.items()))}  (真 ADS-B 应集中在 17/18/19/20/21)")
else:
    print("DF 分布: 无 (全部是噪声)")

# 3. 脉冲间隔分析: 如果脉冲间隔集中在 ~1us/8us 有规律, 是信号; 随机则是噪声
if len(pulses) > 1:
    starts = np.array([s for s, _ in pulses])
    gaps = np.diff(starts) / FS * 1e6
    print(f"\n脉冲间隔 (us): 中位={np.median(gaps):.2f} p90={np.percentile(gaps,90):.2f}")
    print(f"间隔 <1.5us 比例: {np.mean(gaps < 1.5)*100:.1f}%  (ADS-B 数据位间隔 ~1us)")
