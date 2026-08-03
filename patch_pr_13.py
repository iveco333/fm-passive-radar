# -*- coding: utf-8 -*-
"""增加 ADS-B 位置外推: 把飞机按速度外推到 FM 采集时刻, 解决时间不同步"""
import io

path = r"C:\Users\iveco\.openclaw\workspace\passive_radar\pr_rsp1_parallel_multi.py"
s = io.open(path, encoding="utf-8").read()

# 1. main() 里记录采集时间, 传给 step3
old = '''    adsb_local, adsb_time = result
    data_file = step2_rsp1()
    if data_file is None:
        return
    matches, report_file, sample_time, ps = step3_process(data_file, adsb_local, adsb_time)'''
new = '''    adsb_local, adsb_time = result
    import datetime as _dt
    t_adsb = _dt.datetime.strptime(adsb_time, '%Y-%m-%d %H:%M:%S') if adsb_time else None
    data_file = step2_rsp1()
    if data_file is None:
        return
    t_capture = _dt.datetime.now()
    # 外推时间差: FM采集时刻 - ADS-B快照时刻 (秒)
    extrap_sec = (t_capture - t_adsb).total_seconds() if t_adsb else 0.0
    log(f"  [时间] ADS-B快照 -> FM采集 外推 {extrap_sec:.0f}s")
    matches, report_file, sample_time, ps = step3_process(data_file, adsb_local, adsb_time, extrap_sec)'''
assert old in s, "main block not found"
s = s.replace(old, new, 1)

# 2. step3_process 签名加 extrap_sec
old2 = "def step3_process(data_file, adsb_local, adsb_time):"
new2 = "def step3_process(data_file, adsb_local, adsb_time, extrap_sec=0.0):"
assert old2 in s
s = s.replace(old2, new2, 1)

# 3. 飞机循环里加位置外推
old3 = '''        lat, lon = a['lat'], a['lon']
        gs = a.get('gs', 0)
        track = a.get('track', 0)
        alt_raw = a.get('alt_baro', '?')
        flight = a.get('flight', '?').strip()'''
new3 = '''        lat, lon = a['lat'], a['lon']
        gs = a.get('gs', 0)
        track = a.get('track', 0)
        alt_raw = a.get('alt_baro', '?')
        flight = a.get('flight', '?').strip()
        # 位置外推: 按速度/航向移动到 FM 采集时刻
        if extrap_sec > 0 and gs > 0:
            v_mps = gs * 0.514444
            dist_m = v_mps * extrap_sec
            brng = track
            # 经纬度移动 (近似球面)
            dlat = dist_m * math.cos(math.radians(brng)) / 111320.0
            dlon = dist_m * math.sin(math.radians(brng)) / (111320.0 * math.cos(math.radians(lat)) + 1e-9)
            lat += dlat
            lon += dlon'''
assert old3 in s, "aircraft loop not found"
s = s.replace(old3, new3, 1)

io.open(path, "w", encoding="utf-8").write(s)
print("extrapolation added")
