# -*- coding: utf-8 -*-
"""外推时间改为采集中间时刻 (采集开始 + DURATION/2)"""
import io

path = r"C:\Users\iveco\.openclaw\workspace\passive_radar\pr_rsp1_parallel_multi.py"
s = io.open(path, encoding="utf-8").read()

# 1. step2_rsp1 记录采集开始时间并返回
old = '''    with SDRplayAPI() as sdr:
        sdr.select_device(0)
        sdr.set_frequency(FREQ)
        sdr.set_sample_rate(FS)
        sdr.set_gain(RSP1_GRDB)
        log("[RSP1] 开始采集...")
        iq = sdr.capture(DURATION)
        log(f"[RSP1] {len(iq)} 样本 ({len(iq)/FS:.1f}s)")
    raw = np.zeros(len(iq) * 2, dtype=np.uint8)'''
new = '''    t_cap_start = datetime.datetime.now()  # 采集开始时刻
    with SDRplayAPI() as sdr:
        sdr.select_device(0)
        sdr.set_frequency(FREQ)
        sdr.set_sample_rate(FS)
        sdr.set_gain(RSP1_GRDB)
        log("[RSP1] 开始采集...")
        iq = sdr.capture(DURATION)
        log(f"[RSP1] {len(iq)} 样本 ({len(iq)/FS:.1f}s)")
    raw = np.zeros(len(iq) * 2, dtype=np.uint8)'''
assert old in s, "step2 block not found"
s = s.replace(old, new, 1)

# step2 返回值: 找到 return data_file 改成返回 (data_file, t_cap_start)
old2 = "    raw.tofile(data_file)\n    log(f\"[RSP1] 保存: {data_file}\")\n    return data_file"
new2 = "    raw.tofile(data_file)\n    log(f\"[RSP1] 保存: {data_file}\")\n    return data_file, t_cap_start"
assert old2 in s, "step2 return not found"
s = s.replace(old2, new2, 1)

# 2. main 里用采集中间时刻
old3 = '''    t_adsb = _dt.datetime.strptime(adsb_time, '%Y-%m-%d %H:%M:%S') if adsb_time else None
    data_file = step2_rsp1()
    if data_file is None:
        return
    t_capture = _dt.datetime.now()
    # 外推时间差: FM采集时刻 - ADS-B快照时刻 (秒)
    extrap_sec = (t_capture - t_adsb).total_seconds() if t_adsb else 0.0
    log(f"  [时间] ADS-B快照 -> FM采集 外推 {extrap_sec:.0f}s")'''
new3 = '''    t_adsb = _dt.datetime.strptime(adsb_time, '%Y-%m-%d %H:%M:%S') if adsb_time else None
    data_file, t_cap_start = step2_rsp1()
    if data_file is None:
        return
    # 外推目标 = 采集中间时刻 (采集开始 + 时长/2), 比采集完成时刻更准
    t_mid = t_cap_start + _dt.timedelta(seconds=DURATION / 2.0)
    extrap_sec = (t_mid - t_adsb).total_seconds() if t_adsb else 0.0
    log(f"  [时间] ADS-B快照 -> 采集中间 外推 {extrap_sec:.0f}s")'''
assert old3 in s, "main extrap block not found"
s = s.replace(old3, new3, 1)

io.open(path, "w", encoding="utf-8").write(s)
print("mid-capture extrapolation done")
