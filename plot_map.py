"""西安真实地图底图 + 双基地几何 + 飞机 GCR7642 位置"""
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.patches import Ellipse
import requests
from PIL import Image
import io, math

# ---- 坐标 ----
TX = (108.954, 34.201)          # 发射台 (lon, lat)
RX = (108.940, 34.250)          # 接收点
AC = (108.9795, 34.41069)       # GCR7642 (lon, lat)

# ---- OSM 瓦片下载 ----
def deg2num(lat, lon, zoom):
    lat_r = math.radians(lat)
    n = 2**zoom
    xt = (lon + 180.0) / 360.0 * n
    yt = (1.0 - math.asinh(math.tan(lat_r)) / math.pi) / 2.0 * n
    return int(xt), int(yt)

def num2deg(xt, yt, zoom):
    n = 2**zoom
    lon = xt / n * 360.0 - 180.0
    lat = math.degrees(math.atan(math.sinh(math.pi * (1 - 2 * yt / n))))
    return lat, lon

ZOOM = 12
# 视野: 覆盖 AC 与 TX/RX (北到34.43, 南到34.17, 西108.88, 东109.00)
lat_n, lat_s, lon_w, lon_e = 34.43, 34.17, 108.88, 109.00
xt0, yt0 = deg2num(lat_n, lon_w, ZOOM)
xt1, yt1 = deg2num(lat_s, lon_e, ZOOM)
print(f"tiles x:{xt0}..{xt1} y:{yt0}..{yt1}")

tiles = {}
for xt in range(xt0, xt1+1):
    for yt in range(yt0, yt1+1):
        url = f"https://tile.openstreetmap.org/{ZOOM}/{xt}/{yt}.png"
        for attempt in range(3):
            try:
                r = requests.get(url, timeout=20, headers={'User-Agent': 'bistatic-radar-plot/1.0'})
                if r.status_code == 200:
                    tiles[(xt,yt)] = Image.open(io.BytesIO(r.content)).convert('RGB')
                    break
            except Exception as e:
                if attempt == 2: print(f"tile {xt},{yt} fail: {e}")
print(f"tiles fetched: {len(tiles)}")

# 拼接
w = (xt1-xt0+1)*256; h = (yt1-yt0+1)*256
mosaic = Image.new('RGB', (w, h))
for (xt,yt), img in tiles.items():
    mosaic.paste(img, ((xt-xt0)*256, (yt-yt0)*256))
arr = np.array(mosaic)

# 瓦片经纬度范围
lat_top, lon_left = num2deg(xt0, yt0, ZOOM)
lat_bot, lon_right = num2deg(xt1+1, yt1+1, ZOOM)
print(f"extent: lat {lat_bot:.4f}..{lat_top:.4f} lon {lon_left:.4f}..{lon_right:.4f}")

# ---- 绘图 ----
fig, ax = plt.subplots(figsize=(12, 11))
ax.imshow(arr, extent=[lon_left, lon_right, lat_bot, lat_top], aspect='auto', zorder=0)

# 经纬度->像素km比例 (近似, 用于椭圆)
def km_per_deg():
    lat0 = 0.5*(lat_bot+lat_top)
    return 111.32*math.cos(math.radians(lat0)), 110.57
kpx, kpy = km_per_deg()

# 椭圆族 (双基地等距线) - 用极坐标生成点再转经纬度
c_lon = 0.5*(TX[0]+RX[0]); c_lat = 0.5*(TX[1]+RX[1])
f = 0.5*math.hypot((RX[0]-TX[0])*kpx, (RX[1]-TX[1])*kpy)  # 半焦距 km
ang = math.degrees(math.atan2((RX[1]-TX[1])*kpy, (RX[0]-TX[0])*kpx))
for Rsum in [10, 15, 20, 30, 40, 55, 70]:
    a = 0.5*Rsum
    b = math.sqrt(max(a*a - f*f, 0.01))
    # 椭圆参数方程 -> km -> lon/lat
    th = np.linspace(0, 2*np.pi, 200)
    xk = a*np.cos(th); yk = b*np.sin(th)
    # 旋转
    c, s = math.cos(math.radians(ang)), math.sin(math.radians(ang))
    xr = c*xk - s*yk; yr = s*xk + c*yk
    lon = c_lon + xr/kpx; lat = c_lat + yr/kpy
    ax.plot(lon, lat, color='darkblue', lw=1.2, alpha=0.75, zorder=3)
    # 标注
    li = 25
    ax.text(lon[li], lat[li], f'{Rsum}km', fontsize=8, color='darkblue', alpha=0.9)

# 角平分线方向场 (少量箭头, 地图上)
gx = np.linspace(max(lon_w, TX[0]-0.08), min(lon_e, RX[0]+0.08), 9)
gy = np.linspace(lat_bot+0.005, lat_top-0.005, 9)
for lo in gx:
    for la in gy:
        p = np.array([lo, la])
        dT = np.array([(TX[0]-lo)*kpx, (TX[1]-la)*kpy])
        dR = np.array([(RX[0]-lo)*kpx, (RX[1]-la)*kpy])
        nT = np.linalg.norm(dT); nR = np.linalg.norm(dR)
        if nT < 1e-6 or nR < 1e-6: continue
        uT = dT/nT; uR = dR/nR
        bis = uT + uR
        nb = np.linalg.norm(bis)
        if nb < 1e-6: continue
        bis = bis/nb
        ax.arrow(lo, la, bis[0]*0.010/kpx*0.5, bis[1]*0.010/kpy*0.5,
                 color='green', alpha=0.5, width=0.00015, head_width=0.0006, zorder=4)

# 发射机 / 接收机
ax.plot(*TX, 'r^', markersize=15, zorder=6, label='TX 发射台 (108.954, 34.201)')
ax.plot(*RX, 'bs', markersize=13, zorder=6, label='RX 接收点 (108.940, 34.250)')
ax.plot([TX[0], RX[0]], [TX[1], RX[1]], 'k--', lw=1.0, zorder=5, label='基线 5.6 km')

# GCR7642
ax.plot(*AC, 'm*', markersize=22, zorder=7, label='GCR7642 @ 8625ft (108.9795, 34.4107)')
ax.annotate('GCR7642\n18.2km @ 11deg\nhdg 325 (calc)',
            xy=AC, xytext=(AC[0]-0.02, AC[1]-0.012),
            fontsize=9, color='magenta', fontweight='bold',
            arrowprops=dict(arrowstyle='->', color='magenta'), zorder=8)

# 基线中垂线参考
mid = ((TX[0]+RX[0])/2, (TX[1]+RX[1])/2)
dx = RX[0]-TX[0]; dy = (RX[1]-TX[1])*kpy/kpx
ax.plot([mid[0]-dy*0.06, mid[0]+dy*0.06], [mid[1]+dx*0.06*kpy/kpx*0, mid[1]-dx*0.06], 'c:', lw=1, zorder=4, alpha=0.0)

ax.set_xlim(lon_w, lon_e); ax.set_ylim(lat_bot, lat_top)
ax.set_xlabel('Longitude'); ax.set_ylabel('Latitude')
ax.set_title('Xi\'an bistatic geometry (OSM base) - GCR7642, TX, RX, ellipses, bisector field')
ax.legend(loc='lower left', fontsize=9)
ax.grid(alpha=0.15, zorder=1)
fig.tight_layout()
out = r'C:\Users\iveco\.openclaw\workspace\passive_radar\bistatic_map.png'
fig.savefig(out, dpi=130)
print('saved', out)
