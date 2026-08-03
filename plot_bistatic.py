"""双基地雷达几何可视化: 角平分线方向场 + 零多普勒方向 + 椭圆族"""
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

# ---- 坐标 (西安实测: 发射台+接收点, 基线5.6km) ----
TX = np.array([108.954, 34.201])   # (lon, lat)
RX = np.array([108.940, 34.250])

# 经纬度 -> 局部 km (TX为原点, X向东, Y向北)
def to_km(p):
    dlon = (p[0] - TX[0]) * 111.32 * np.cos(np.radians(TX[1]))
    dlat = (p[1] - TX[1]) * 110.57
    return np.array([dlon, dlat])

TXk = to_km(TX)
RXk = to_km(RX)

# ---- 网格 (km) ----
gx = np.linspace(-14, 20, 120)
gy = np.linspace(-14, 20, 120)
X, Y = np.meshgrid(gx, gy)

# 到两焦点的单位向量场
u = np.zeros_like(X); v = np.zeros_like(Y)
for i in range(X.shape[0]):
    for j in range(X.shape[1]):
        p = np.array([X[i,j], Y[i,j]])
        dT = TXk - p; dR = RXk - p
        nT = np.linalg.norm(dT); nR = np.linalg.norm(dR)
        if nT < 1e-6 or nR < 1e-6:
            u[i,j] = v[i,j] = 0
            continue
        uT = dT/nT; uR = dR/nR
        u[i,j] = uT[0] + uR[0]      # 角平分线方向 = 单位向量之和
        v[i,j] = uT[1] + uR[1]

# ---- 图 ----
fig, ax = plt.subplots(figsize=(11, 9))

# 1. 椭圆族: R_T + R_R = const (双基地距离等值线)
for Rsum in [10, 15, 20, 30, 40, 55]:
    ell = plt.matplotlib.patches.Ellipse(
        (0.5*(TXk[0]+RXk[0]), 0.5*(TXk[1]+RXk[1])),
        width=Rsum, height=np.sqrt(Rsum**2 - 5.6**2),
        angle=np.degrees(np.arctan2(RXk[1]-TXk[1], RXk[0]-TXk[0])),
        fill=False, edgecolor='lightgray', lw=1.0)
    ax.add_patch(ell)
    # 标注
    mx = 0.5*(TXk[0]+RXk[0]) + 0.5*Rsum*np.cos(np.radians(15))
    my = 0.5*(TXk[1]+RXk[1]) + 0.5*Rsum*np.sin(np.radians(15))
    ax.text(mx, my, f'{Rsum} km', color='gray', fontsize=8, ha='left')

# 2. 角平分线方向场 (绿色箭头)
step = 7
ax.quiver(X[::step,::step], Y[::step,::step], u[::step,::step], v[::step,::step],
          color='green', alpha=0.55, scale=60, width=0.004,
          label='Bisector direction (u_TX + u_RX)')

# 3. 角平分线方向场的流线 (积分曲线 = 角平分线"轨迹")
#    归一化场用于流线
mag = np.hypot(u, v) + 1e-9
ax.streamplot(X, Y, u/mag, v/mag, color='darkgreen', linewidth=1.2, density=1.6, arrowsize=1.2)

# 4. 发射机 / 接收机
ax.plot(*TXk, 'r^', markersize=14, label='TX (FM transmitter)')
ax.plot(*RXk, 'bs', markersize=12, label='RX (RSP1 receiver)')
ax.plot([TXk[0], RXk[0]], [TXk[1], RXk[1]], 'k--', lw=1.0, label='Baseline 5.6 km')

# 5. 示例: 某点处 角平分线 vs 零多普勒方向
for px, py, tag in [(-8, 12, 'A'), (14, 4, 'B'), (0, -10, 'C')]:
    p = np.array([px, py])
    dT = TXk - p; dR = RXk - p
    uT = dT/np.linalg.norm(dT); uR = dR/np.linalg.norm(dR)
    bis = uT + uR                       # 角平分线方向
    bis = bis/np.linalg.norm(bis)
    zero = np.array([-bis[1], bis[0]])  # 垂直 = 零多普勒方向
    ax.arrow(px, py, bis[0]*3, bis[1]*3, color='lime', width=0.18, head_width=0.6, length_includes_head=True)
    ax.arrow(px, py, zero[0]*3, zero[1]*3, color='orange', width=0.18, head_width=0.6, length_includes_head=True)
    ax.text(px, py, f'  {tag}: bisector(lime) / zero-Doppler(orange)', fontsize=8,
            color='black', va='center')

ax.set_xlabel('East (km from TX)')
ax.set_ylabel('North (km from TX)')
ax.set_title('Bistatic radar geometry: ellipse family, bisector field (green), zero-Doppler dir (orange)')
ax.set_aspect('equal')
ax.legend(loc='upper left', fontsize=9)
ax.grid(alpha=0.2)
fig.tight_layout()
fig.savefig(r'C:\Users\iveco\.openclaw\workspace\passive_radar\bistatic_geometry.png', dpi=130)
print('saved bistatic_geometry.png')
