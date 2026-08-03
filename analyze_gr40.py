"""分析 gRdB=40 全部运行 (10:32 起), 统计匹配率/原因/质量"""
import os, re, glob

base = r'C:\Users\iveco\.openclaw\workspace\passive_radar'

# gRdB=40 的报告: 103216 103252 103328 103405 103441 (10:32-10:35) + 11:08 之后全部
files = sorted(glob.glob(os.path.join(base, 'pr_parallel_20260802_1*.md')))
files += [os.path.join(base, f) for f in ['pr_parallel_20260802_103216.md','pr_parallel_20260802_103252.md',
                                          'pr_parallel_20260802_103328.md','pr_parallel_20260802_103405.md',
                                          'pr_parallel_20260802_103441.md']]
files = sorted(set(files))

total_adsb = 0; total_ok = 0; total_no = 0
ok_entries = []       # (file, callsign, dist_diff, dop_diff)
no_reasons = {}       # reason -> count
no_entries = []       # (callsign, bi_km, nearest_pr, reason)

for f in files:
    with open(f, encoding='utf-8', errors='replace') as fh:
        txt = fh.read()
    name = os.path.basename(f)
    # ADS-B 行: | CALLSIGN | alt | spd | hdg | hdist | sdist | brg | bi | fd |
    for line in txt.split('\n'):
        m = re.match(r'^\| ([A-Z0-9?]{3,}) \|', line)
        if m and '---' not in line:
            total_adsb += 1
    # 匹配行: - CALLSIGN: PR=.. ADS-B=.. 频差XHz
    for line in txt.split('\n'):
        m = re.match(r'^- ([A-Z0-9?]+): PR=([0-9.]+)km/([+-][0-9]+)Hz ADS-B=([0-9.]+)km/([+-][0-9]+)Hz', line)
        if m:
            total_ok += 1
            dd = abs(float(m.group(4)) - float(m.group(2)))
            fd = abs(int(m.group(5)) - int(m.group(3)))
            ok_entries.append((name, m.group(1), dd, fd))

print(f"文件数: {len(files)}")
print(f"ADS-B 参照总数: {total_adsb}")
print(f"匹配数: {total_ok}  ({total_ok/max(total_adsb,1)*100:.0f}%)")
print()
print("=== 匹配明细 ===")
for name, cs, dd, fd in ok_entries:
    print(f"  {name[13:25]} {cs}: dist_diff={dd:.1f}km dop_diff={fd}Hz")
if ok_entries:
    dds = [e[2] for e in ok_entries]; fds = [e[3] for e in ok_entries]
    print(f"  平均距离差: {sum(dds)/len(dds):.2f}km | 平均多普勒差: {sum(fds)/len(fds):.0f}Hz")
print()
print("=== 未匹配原因 ===")
# 从 [NO] 行提取
for f in files:
    with open(f, encoding='utf-8', errors='replace') as fh:
        for line in fh:
            m = re.search(r'reason: (.+)', line)
            if m:
                r = m.group(1)
                no_reasons[r] = no_reasons.get(r, 0) + 1
for r, c in sorted(no_reasons.items(), key=lambda x: -x[1]):
    print(f"  {c:2d}x  {r}")
