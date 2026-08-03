#!/usr/bin/env python3
"""NOAA 19 过境自动接收 (Windows) - 2026-08-01 21:41 CST
录制 137.9125 MHz 12 分钟, 自动 satdump 解码
"""
import subprocess, sys, os, time

BASE = os.path.dirname(os.path.abspath(__file__))
STAMP = time.strftime("%Y%m%d_%H%M%S")
RAW = os.path.join(BASE, f"noaa19_{STAMP}.wav")
OUT = os.path.join(BASE, f"noaa19_{STAMP}_out")

# 1. 录制 720 秒
print(f"[{time.strftime('%H:%M:%S')}] 开始录制 NOAA 19 @ 137.9125 MHz ...", flush=True)
r = subprocess.run([sys.executable, os.path.join(BASE, "record_apt_win.py"), "137.9125", "720", RAW])
if r.returncode != 0 or not os.path.exists(RAW):
    print("录制失败!", flush=True)
    sys.exit(1)
print(f"[{time.strftime('%H:%M:%S')}] 录制完成, 开始解码...", flush=True)

# 2. 解码
os.makedirs(OUT, exist_ok=True)
sat = os.path.join(BASE, "satdump_win", "satdump.exe")
r = subprocess.run([sat, "noaa_apt", "baseband", RAW, OUT, "--samplerate", "250000", "--baseband_format", "cf32"],
                   capture_output=True, text=True)
pngs = [f for f in os.listdir(OUT) if f.endswith(".png")]
print(f"[{time.strftime('%H:%M:%S')}] 解码完成: {len(pngs)} 张图 -> {OUT}", flush=True)
print("结果文件:", pngs, flush=True)
