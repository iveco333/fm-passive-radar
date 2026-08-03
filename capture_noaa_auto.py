#!/usr/bin/env python3
"""气象卫星自动录制+解码 (satdump live 直驱 SDRplay)
用法: python capture_noaa_auto.py <频率MHz> <时长s> <卫星名>
  NOAA15: 137.620 MHz
  NOAA18: 137.9125 MHz
  NOAA19: 137.100 MHz
关键: 用 satdump live 模式, 采样率由 satdump 自己管理 (绕开 sdrplay_api.py 的 fsHz bug)
"""
import subprocess, sys, os, time

BASE = os.path.dirname(os.path.abspath(__file__))
freq_mhz = float(sys.argv[1]) if len(sys.argv) > 1 else 137.9125
duration = int(sys.argv[2]) if len(sys.argv) > 2 else 720
sat_name = sys.argv[3] if len(sys.argv) > 3 else "NOAA"

STAMP = time.strftime("%Y%m%d_%H%M%S")
OUT = os.path.join(BASE, f"{sat_name.lower()}_{STAMP}_out")

print(f"[{time.strftime('%H:%M:%S')}] 开始录制 {sat_name} @ {freq_mhz} MHz, {duration}s ...", flush=True)

sat = os.path.join(BASE, "satdump_win", "satdump.exe")
cmd = [sat, "live", "noaa_apt", OUT,
       "--source", "sdrplay",
       "--samplerate", "2e6",
       "--frequency", f"{freq_mhz}e6",
       "--gain", "30",
       "--timeout", str(duration)]
print("  $ " + " ".join(cmd), flush=True)
r = subprocess.run(cmd, cwd=os.path.join(BASE, "satdump_win"))
if r.returncode != 0:
    print("satdump 失败!", flush=True)
    sys.exit(1)

pngs = []
if os.path.isdir(OUT):
    pngs = [f for f in os.listdir(OUT) if f.endswith(".png")]
print(f"[{time.strftime('%H:%M:%S')}] 解码完成: {len(pngs)} 张图 -> {OUT}", flush=True)
print("结果文件:", pngs, flush=True)
if pngs:
    print("图片路径:", [os.path.join(OUT, p) for p in pngs], flush=True)
