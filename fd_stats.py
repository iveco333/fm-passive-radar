#!/usr/bin/env python3
"""统计: 实测目标的多普勒分布 (判断 0Hz 屏蔽区该多宽)"""
import json, math, glob

def haversine(l1, o1, l2, o2):
    R = 6371
    a = math.sin(math.radians(l2-l1)/2)**2 + math.cos(math.radians(l1))*math.cos(math.radians(l2))*math.sin(math.radians(o2-o1)/2)**2
    return R*2*math.atan2(math.sqrt(a), math.sqrt(1-a))
def bearing(lat1, lon1, lat2, lon2):
    dlon = math.radians(lon2-lon1)
    lat1, lat2 = math.radians(lat1), math.radians(lat2)
    x = math.sin(dlon)*math.cos(lat2)
    y = math.cos(lat1)*math.sin(lat2) - math.sin(lat1)*math.cos(lat2)*math.cos(dlon)
    return (math.degrees(math.atan2(x, y))+360) % 360
TX = (34.201, 108.954); RX = (34.25, 108.94)
lam = 3e8/87.5e6
tx_rx = haversine(TX[0], TX[1], RX[0], RX[1])

fds = []
for f in sorted(glob.glob('adsb_2026080[23]_*.json')):
    try:
        d = json.load(open(f))
    except Exception:
        continue
    for a in d.get('aircraft', []):
        if 'lat' not in a or 'lon' not in a: continue
        gs = a.get('gs', 0); tr = a.get('track', 0)
        if gs <= 0: continue
        lat, lon = a['lat'], a['lon']
        v = gs*0.514444
        vx = v*math.sin(math.radians(tr)); vy = v*math.cos(math.radians(tr))
        tg = haversine(TX[0], TX[1], lat, lon); rg = haversine(RX[0], RX[1], lat, lon)
        alt = float(a.get('alt_baro', 0) or 0)*0.3048
        ts = math.sqrt(tg**2+(alt/1000)**2); rs = math.sqrt(rg**2+(alt/1000)**2)
        bt = bearing(TX[0], TX[1], lat, lon); br = bearing(RX[0], RX[1], lat, lon)
        cet = tg/ts if ts>0 else 1.0; cer = rg/rs if rs>0 else 1.0
        th = (math.sin(math.radians(bt))*cet, math.cos(math.radians(bt))*cet)
        rh = (math.sin(math.radians(br))*cer, math.cos(math.radians(br))*cer)
        fd = -(vx*(th[0]+rh[0]) + vy*(th[1]+rh[1])) / lam
        fds.append((abs(fd), fd, a.get('flight','?'), gs, a.get('alt_baro','?')))

fds.sort()
print(f'共 {len(fds)} 个目标, 按 |多普勒| 升序前 20:')
print(f'{"fd":>7} {"|fd|":>5} {"航班":>9} {"kts":>5} {"alt":>7}')
for afd, fd, fl, gs, alt in fds[:20]:
    print(f'{fd:+6.0f} {afd:5.0f} {fl:>9} {gs:5.0f} {str(alt):>7}')
print()
for thr in [5, 10, 15, 20, 25, 30]:
    print(f'|fd| < {thr:2d}Hz: {sum(1 for x in fds if x[0]<thr):3d} 个 ({sum(1 for x in fds if x[0]<thr)*100//len(fds)}%)')
