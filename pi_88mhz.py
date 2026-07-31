"""Pi 88 MHz FM Passive Radar with modified parameters."""
import sys, time, numpy as np
sys.path.insert(0, "/home/iveco/passive_radar_backup/pi_scripts")
from passive_radar import read_iq, batch_cross_ambiguity
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

filename = "/tmp/pi_88.dat"
center_freq = 88e6
fs = 2.0e6

print("Loading...")
iq = read_iq(filename)
print("Loaded %d samples (%.1fs)" % (len(iq), len(iq)/fs))

# Longer integration
ref_duration = 0.5
sig_duration = 0.5
ref_len = int(ref_duration * fs)
sig_len = int(sig_duration * fs)

reference = iq[:ref_len]
signal = iq[ref_len//2:ref_len//2 + sig_len]
print("Ref: %ds, Sig: %ds" % (ref_duration, sig_duration))

max_delay = 300
doppler_freqs = np.linspace(-100, 100, 31)

print("CAF: %d bins x %d delay..." % (len(doppler_freqs), max_delay))
t0 = time.time()
result = batch_cross_ambiguity(signal, reference, max_delay, doppler_freqs)
print("Done in %.0fs" % (time.time()-t0))

delays = np.arange(max_delay)
range_km = delays / fs * 3e8 / 1000
result_db = 20 * np.log10(np.maximum(result, 1e-10))
result_db -= result_db.max()

fig, ax = plt.subplots(figsize=(12, 8))
im = ax.pcolormesh(range_km, doppler_freqs, result_db, shading="auto", cmap="turbo", vmin=-25, vmax=0)
plt.colorbar(im, ax=ax, label="dB")
ax.set_xlabel("Bistatic Range (km)")
ax.set_ylabel("Doppler (Hz)")
ax.set_title("Pi 88MHz FM PR (%.1fs+%.1fs)" % (ref_duration, sig_duration))
plt.tight_layout()
plt.savefig("/tmp/pr_88_result.png", dpi=120)
print("Saved: /tmp/pr_88_result.png")

print("\nTop peaks (non-zero Doppler):")
center_d = len(doppler_freqs)//2
for di in range(len(doppler_freqs)):
    if abs(di - center_d) <= 1:
        continue
    for ri in range(max_delay):
        if result_db[di,ri] > -18:
            print("  %.0fHz  %.1fkm  %.1fdB" % (doppler_freqs[di], range_km[ri], result_db[di,ri]))
