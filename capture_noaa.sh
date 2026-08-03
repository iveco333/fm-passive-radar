#!/bin/bash
# NOAA APT 自动接收: 过境前开始录制, 录完自动用 satdump 解码
# 用法: capture_noaa.sh <卫星名> <频率MHz> <UTC过境时间>
# 例:   capture_noaa.sh "NOAA 19" 137.9125 "2026-08-01 03:59:00"

SAT_NAME="$1"
FREQ="$2"
PASS_TIME_UTC="$3"

DIR="/home/iveco/noaa"
STAMP=$(date -u +%Y%m%d_%H%M%S)
RECFILE="$DIR/raw/${SAT_NAME// /_}_${STAMP}.wav"
OUTDIR="$DIR/decoded/${SAT_NAME// /_}_${STAMP}"

mkdir -p "$DIR/raw" "$DIR/decoded"

echo "[$(date '+%F %T')] 开始录制 $SAT_NAME @ $FREQ MHz (过境 $PASS_TIME_UTC UTC)"

# 过境前 30 秒开始, 录 12 分钟 (典型过境 10 分钟)
# 用 sleep 到目标时间前 30 秒
TARGET_EPOCH=$(date -u -d "$PASS_TIME_UTC" +%s 2>/dev/null)
NOW_EPOCH=$(date -u +%s)
SLEEP_SEC=$((TARGET_EPOCH - 30 - NOW_EPOCH))

if [ "$SLEEP_SEC" -gt 0 ]; then
    echo "等待 $SLEEP_SEC 秒后开始录制..."
    sleep "$SLEEP_SEC"
fi

# 录制 720 秒 (12 分钟)
python3 /home/iveco/noaa/record_apt.py "$FREQ" 720 "$RECFILE"
REC_OK=$?

if [ "$REC_OK" -eq 0 ] && [ -f "$RECFILE" ]; then
    echo "[$(date '+%F %T')] 录制完成, 开始解码..."
    satdump noaa_apt baseband "$RECFILE" "$OUTDIR" --samplerate 250000 --baseband_format cf32 > /dev/null 2>&1
    echo "[$(date '+%F %T')] 解码完成: $OUTDIR"
    # 保留最强的图
    ls "$OUTDIR"/*.png 2>/dev/null | head -1
else
    echo "[$(date '+%F %T')] 录制失败"
fi
