#!/usr/bin/env python3
"""一次性 ADS-B 解码测试: 采 5 秒, 尝试解码, 输出结果后退出"""
import sys, os, time
import numpy as np
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from sdrplay_api import SDRplayAPI
import pyModeS as pms

FREQ = 1090e6
FS = 2.4e6
GAIN = 30

sdr = SDRplayAPI()
sdr.select_device(0)
sdr.set_frequency(FREQ)
sdr.set_sample_rate(FS)
sdr.set_gain(GAIN)
print("capturing 5s...", flush=True)
iq = sdr.capture(5.0)
sdr.close()
print(f"captured {len(iq)} samples", flush=True)

mag = np.abs(iq)
thr = np.percentile(mag, 99.5) * 1.2

# 找前导脉冲: 4 脉冲模式 0,1,2,3.5us
fs_mhz = FS / 1e6
bit_samples = int(fs_mhz)  # 1us
preamble_offsets = [0, 1, 2, 3.5]
preamble_idx = [int(o * fs_mhz) for o in preamble_offsets]

above = mag > thr
n = len(mag)
found = 0
msgs = []
for i in range(100, n - 200):
    if not above[i]:
        continue
    # 检查前导: i, i+1us, i+2us, i+3.5us 都是脉冲, 中间不是
    try:
        if above[i + preamble_idx[1]] and above[i + preamble_idx[2]] and above[i + preamble_idx[3]]:
            if not above[i + bit_samples // 2] and not above[i + bit_samples + bit_samples // 2]:
                # 解码 112 位
                bits = []
                for b in range(112):
                    s = i + 8 * bit_samples + b * bit_samples
                    if s + bit_samples >= n:
                        break
                    win = mag[s:s + bit_samples]
                    bits.append(1 if np.mean(win) > thr else 0)
                if len(bits) == 112:
                    hex_str = "".join(str(b) for b in bits)
                    try:
                        m = pms.Message(hex_str)
                        d = m.decode()
                        msgs.append(d)
                        found += 1
                        icao = d.get("icao", "?")
                        cs = d.get("callsign", "-")
                        alt = d.get("altitude", "-")
                        print(f"  [{time.strftime('%H:%M:%S')}] {icao} {cs} {alt}", flush=True)
                    except Exception:
                        pass
    except IndexError:
        continue

print(f"\n完成: 检测到 {found} 个有效 ADS-B 消息", flush=True)
if not msgs:
    print("(有脉冲但未能解码出有效消息)", flush=True)
