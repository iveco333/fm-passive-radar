import subprocess, os

base = r'C:\Users\iveco\.openclaw\workspace\passive_radar'

# 换天线位置前 (2s): 095821 095858 095937 100014 100052
# 换天线位置后 (2s): 100332 100409 100447 100524 100602
cases_before = [
    ('fm_rsp1_20260802_095821.dat', 'before 095821'),
    ('fm_rsp1_20260802_095858.dat', 'before 095858'),
    ('fm_rsp1_20260802_095937.dat', 'before 095937'),
    ('fm_rsp1_20260802_100014.dat', 'before 100014'),
    ('fm_rsp1_20260802_100052.dat', 'before 100052'),
]
cases_after = [
    ('fm_rsp1_20260802_100332.dat', 'after  100332'),
    ('fm_rsp1_20260802_100409.dat', 'after  100409'),
    ('fm_rsp1_20260802_100447.dat', 'after  100447'),
    ('fm_rsp1_20260802_100524.dat', 'after  100524'),
    ('fm_rsp1_20260802_100602.dat', 'after  100602'),
]

def run_all(cases, label):
    print(f"########## {label} ##########")
    for fname, tag in cases:
        p = os.path.join(base, fname)
        if os.path.exists(p):
            r = subprocess.run(['python', 'snr_real.py', fname, '1.0', '1.0'],
                               cwd=base, capture_output=True, text=True)
            # 只输出关键行
            lines = r.stdout.strip().split('\n')
            for ln in lines:
                if any(k in ln for k in ['输入信号', '峰-噪比', '峰值位置']):
                    print(f"[{tag}] {ln.strip()}")
        else:
            print(f"[{tag}] MISSING {fname}")
    print()

run_all(cases_before, '换天线前 (09:58-10:01)')
run_all(cases_after, '换天线后 (10:03-10:06)')
