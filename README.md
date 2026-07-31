# FM 被动雷达 (Passive Coherent Location)

用 **FM 广播信号作为机会照射源** 检测飞机的无源雷达系统。双基地配置(bistatic radar):
FM 发射塔照射 → 飞机反射 → 接收机捕获回波,通过 **互模糊函数 (Cross-Ambiguity Function, CAF)** 同时估计双基地距离和多普勒频移,再用 **ADS-B 真值** 交叉验证。

> 西安 · 个人 SDR 实验项目。从树莓派 RTL-SDR 起步,最终跑在 Windows + SDRplay RSP1 上。

---

## 原理

```
              FM 发射塔 (88~108 MHz)
                  │ 直达波 (强, 要抑制)
                  │        ╲ 反射波 (弱, 要检测)
                  ▼         ╲
               接收机 ◄────── 飞机
```

- **双基地距离** `R_b = R_tx→target + R_rx→target − R_tx→rx` —— 由 CAF 的时延维给出
- **多普勒频移** —— 由 CAF 的频率维给出(目标运动 + 双基地几何的 3D 投影)
- **直达波 (DPI) 抑制** —— LMS 自适应滤波,把参考通道里的强直达信号从监视通道中消掉
- **验证** —— 同机位的 ADS-B (1090 MHz) 提供每架飞机的真实位置/速度,算出理论 `R_b` 和 `f_d`,与 CAF 峰值匹配

## 信号处理链

```
IQ 采集 (RSP1 @ ~2 MSPS)
   │
   ▼
预处理: DC 去偏 · 19 kHz 陷波(FM 立体声导频) · 100 kHz 低通
   │
   ▼
DPI 抑制: LMS 自适应滤波 (128 taps, μ=0.002)
   │
   ▼
CAF: 多普勒 ±150 Hz / 61 bins × 时延 0~800 samples (≈120 km), FFT 批处理
   │
   ▼
峰值检测: 屏蔽零多普勒带(直达波), SNR 门限
   │
   ▼
ADS-B 匹配: readsb 快照 → 3D 多普勒 + 双基地距离 → 匹配 (距离±5km, 多普勒±40Hz)
```

## 结果

- **检测到 ~10 个目标**,距离 6–44 km,SNR 10–11 dB(88 MHz,西安)
- 与 ADS-B 真值**匹配成功**,距离/多普勒均对得上(见 `results/` 标注图)
- 88 MHz 是西安本地最强 FM 台(-4.6 dBFS);gRdB=20 为最佳增益
- 用 91.6 MHz 做双台测距,配合 ADS-B 反推了发射台位置(`locate_tx.py`)

| 图 | 说明 |
|----|------|
| `results/pi_final_annotated.png` | 最终结果 + ADS-B 航班标注 |
| `results/pi_annotated.png` | 88 MHz 检测结果 + ADS-B 标注 |
| `results/pi_new2_result.png` | 改进参数后的 CAF 图 |
| `results/pr_new_result_zerodopp.png` | 零多普勒带抑制前后对比 |

## 硬件

| 组件 | 型号 | 职责 |
|------|------|------|
| 接收机 (FM) | SDRplay RSP1 (12-bit ADC) | 87.5–91.6 MHz 采集,~2 MSPS |
| 接收机 (ADS-B) | 树莓派 3B + RTL-SDR | readsb 服务,1090 MHz 快照 |
| 天线 | 拉杆天线 | 参考天线指向发射塔,监视天线指向天空 |
| 处理机 | Windows PC | CAF 处理几秒出结果 |

**为什么从 RTL-SDR 换到 RSP1:**
- RTL-SDR 是 8-bit ADC,动态范围有限,弱回波被淹没
- Pi3B 算力弱,0.5 s CAF 要跑 30–40 s
- RSP1 12-bit ADC → 更高动态范围;PC 算力 → CAF 秒级;SDRplay 官方 Windows 驱动稳定

## 快速开始

```cmd
pip install -r requirements.txt
```

### 文件模式(最快上手,不需要实时采集)

1. SDRuno 打开 RSP1,设频率到当地最强 FM 台(西安用 88 MHz)
2. 带宽 2 MHz,增益 20–30 dB(别太高,避免 ADC 饱和)
3. WRF 按钮 → WAV 格式录 4–10 秒
4. 处理:

```cmd
python passive_radar_windows.py --file recording.wav -o result.png
```

### 实时模式 (Windows + RSP1 + Pi ADS-B 联合)

```cmd
python pr_rsp1.py
```

自动完成:Pi 取 ADS-B 快照 → RSP1 采 FM → LMS/CAF → 峰值检测 → ADS-B 匹配 → 输出 Markdown 报告。

### 跨平台一键脚本 (Pi 采集 + Windows 处理)

```cmd
python pr_cross_platform.py
```

## 文件结构

```
passive_radar/
├── pr_rsp1.py               # 主程序: RSP1 采集 + Pi ADS-B + 处理 + 匹配 + 报告
├── pr_rsp1_parallel.py      # 多核并行版 CAF(提速)
├── pr_cross_platform.py     # 跨平台一键脚本(Pi 采集 / Windows 处理)
├── passive_radar_windows.py # 文件模式(WAV)+ 实时模式(SoapySDR)
├── sdrplay_api.py           # SDRplay API v3.07 ctypes 封装(直调 DLL)
├── pi_pr_v5.py              # Pi 版算法: 频域 DPI + Batch CAF + CLEAN
├── pi_pr_v2.py              # Pi 版算法 v2(LMS 逐点,慢)
├── pi_88mhz.py              # Pi 88 MHz 参数实验
├── adsb_receiver.py         # Windows RSP1 1090 MHz ADS-B 接收(pyModeS)
├── locate_tx.py             # 发射台三角定位
├── verify.py / verify2.py   # PR 检测 vs ADS-B 验证工具
├── annotate_final.py        # 结果图标注 ADS-B
├── adsb_fresh.json          # ADS-B 快照示例
├── results/                 # CAF 结果图
└── requirements.txt
```

## 已知问题 & 教训

- **RSP1 不支持 decimation**(Init 直接失败),采样率只能通过带宽参数控制
  (`BW_1_536` ≈ 1.94 MSPS)
- **1090 MHz 谐波干扰**:ADS-B 天线收到信号但 PPM 解码 CRC 全失败,疑似 88 MHz 的
  12 次谐波(≈1056 MHz)混入 → 需要真正的 1090 MHz 天线或加带通滤波
- **RTL-SDR 8-bit** 动态范围是最大瓶颈;LMS 逐点循环太慢,要改成频域批处理
- CAF 峰值里零多普勒附近全是直达波旁瓣,必须屏蔽后再检测

## 参考

- [blah2](https://github.com/30hours/blah2) — 双通道实时被动雷达(启发)
- [readsb](https://github.com/wiedehopf/readsb) — ADS-B 解码器(Pi 上跑)
- [SDRplay RSP1](https://www.sdrplay.com/rsp1/) — 硬件规格
- 项目笔记: `USER.md` / Obsidian `D:\myobsidian\iveco\SDR\`
