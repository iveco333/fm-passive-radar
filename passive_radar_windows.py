#!/usr/bin/env python3
"""
FM Passive Radar -- Windows + RSP1

Uses Cross-Ambiguity Function (CAF) to detect aircraft from FM broadcast reflections.

Modes:
  --live    Real-time capture from RSP1 (requires SDRplay API driver)
  --file    Process recorded IQ file (raw uint8 or WAV)

Deps: pip install numpy scipy matplotlib soundfile
"""

import argparse
import os
import sys
import time
from pathlib import Path

import numpy as np
from scipy import signal as sp_signal
from scipy.fft import fft, ifft
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

from sdrplay_api import SDRplayAPI


DEFAULT_FREQ = 91.6e6
FS = 2.0e6
DEFAULT_GAIN = 30
INTEG_TIME = 2.0
MAX_DOPPLER = 200
MAX_RANGE = 45000


# ---- IQ I/O ----


def read_raw_uint8(path, n_samples=None):
    raw = np.fromfile(path, dtype=np.uint8)
    samples = (raw.astype(np.float32) - 127.5) / 127.5
    iq = samples[0::2] + 1j * samples[1::2]
    if n_samples and len(iq) > n_samples:
        iq = iq[:n_samples]
    return iq


def read_wav_iq(path, n_samples=None):
    import soundfile as sf
    data, sr = sf.read(path, dtype="float32")
    if data.ndim == 2 and data.shape[1] == 2:
        iq = data[:, 0] + 1j * data[:, 1]
    elif data.ndim == 1:
        iq = data[0::2] + 1j * data[1::2]
    else:
        raise ValueError(f"Bad WAV format: shape={data.shape}")
    if n_samples and len(iq) > n_samples:
        iq = iq[:n_samples]
    return iq


# ---- Signal Processing ----


def remove_dc_block(iq, block=1024):
    out = iq.copy()
    for i in range(0, len(iq), block):
        b = out[i:i + block]
        out[i:i + block] = b - np.mean(b)
    return out


def notch_19k(iq, fs=FS):
    f0 = 19000
    w0 = f0 / (fs / 2)
    b, a = sp_signal.iirnotch(w0, 30.0, fs)
    return sp_signal.filtfilt(b, a, iq)


def cross_ambiguity(surv, ref, max_delay, doppler_bins, n_fft_fac=2):
    n = len(surv)
    n_fft = n // n_fft_fac
    n_chunks = max(1, n // n_fft)
    n_fft = n // n_chunks

    ref_power = np.mean(np.abs(ref) ** 2)
    ref_norm = ref / np.sqrt(ref_power + 1e-10)

    caf = np.zeros((doppler_bins, max_delay), dtype=np.complex64)

    for ci in range(n_chunks):
        s = surv[ci * n_fft:(ci + 1) * n_fft]
        r = ref_norm[ci * n_fft:(ci + 1) * n_fft]
        if len(s) < n_fft:
            break
        R = fft(r, n_fft * 2)
        for d in range(max_delay):
            sd = np.roll(s, d)
            S = fft(sd, n_fft * 2)
            cf = ifft(S * np.conj(R))
            caf[:, d] += cf[:doppler_bins]

    delay_axis = (np.arange(max_delay) * (3e8 / FS)) / 1000
    doppler_axis = np.linspace(-MAX_DOPPLER, MAX_DOPPLER, doppler_bins)
    return doppler_axis, delay_axis, np.abs(caf)


def process(iq, fs=FS):
    print(f"  Signal: {len(iq)} samples ({len(iq)/fs:.1f}s)")
    iq = remove_dc_block(iq)
    iq = notch_19k(iq, fs)
    sos = sp_signal.butter(5, 100e3, "low", fs=fs, output="sos")
    iq = sp_signal.sosfilt(sos, iq)

    split = int(len(iq) * 0.1)
    ref = iq[:split]
    surv = iq[split:]

    max_delay = int(MAX_RANGE / (3e8 / fs))
    doppler_bins = int(MAX_DOPPLER * INTEG_TIME * 2)

    print("  Computing CAF...")
    t0 = time.time()
    dop, dly, caf = cross_ambiguity(surv, ref, max_delay, doppler_bins)
    print(f"  CAF done ({time.time()-t0:.1f}s)")
    return dop, dly, caf


# ---- Plotting ----


def plot_rd(dop_axis, dly_axis, caf, path, title=None):
    caf_db = 20 * np.log10(caf + 1e-10)
    caf_db -= np.max(caf_db)

    plt.figure(figsize=(14, 8))
    extent = [dly_axis[0], dly_axis[-1], dop_axis[0], dop_axis[-1]]
    plt.imshow(caf_db, aspect="auto", origin="lower", extent=extent,
               cmap="inferno", vmin=-30, vmax=0)
    plt.colorbar(label="Normalized amplitude (dB)")
    plt.xlabel("Bistatic range (km)")
    plt.ylabel("Doppler shift (Hz)")
    plt.title(title or "FM Passive Radar -- Range-Doppler Map")
    plt.tight_layout()
    plt.savefig(path, dpi=150)
    print(f"  Output: {path}")
    plt.close()


# ---- Main ----


def main():
    p = argparse.ArgumentParser(
        description="FM Passive Radar -- Windows + RSP1",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    p.add_argument("--file", help="IQ file path")
    p.add_argument("--live", action="store_true", help="Live capture from RSP1")
    p.add_argument("--raw", action="store_true", help="File is raw uint8")
    p.add_argument("-f", "--freq", type=float, default=DEFAULT_FREQ, help="FM freq (Hz)")
    p.add_argument("-g", "--gain", type=float, default=DEFAULT_GAIN, help="Gain dB")
    p.add_argument("-t", "--time", type=float, default=INTEG_TIME, help="Integration time (s)")
    p.add_argument("-o", "--output", default="result.png", help="Output image")
    args = p.parse_args()

    if not args.file and not args.live:
        p.error("Specify --file or --live")
    if args.file and args.live:
        p.error("Can't use both --file and --live")

    print("=" * 50)
    print("FM Passive Radar -- Windows + RSP1")
    print("=" * 50)
    print(f"  Freq: {args.freq/1e6:.1f} MHz")
    print(f"  Integ: {args.time:.1f}s")

    # Capture
    if args.live:
        print("\n[Capture] RSP1 live...")
        with SDRplayAPI() as sdr:
            sdr.select_device(0)
            sdr.set_frequency(args.freq)
            sdr.set_sample_rate(FS)
            sdr.set_gain(args.gain)
            iq = sdr.capture(args.time)
    else:
        ext = Path(args.file).suffix.lower()
        is_raw = args.raw or ext in (".raw", ".dat", ".bin")
        n_samp = int(FS * args.time)
        if is_raw:
            print(f"\n[Read] raw uint8: {args.file}")
            iq = read_raw_uint8(args.file, n_samp)
        else:
            print(f"\n[Read] WAV: {args.file}")
            iq = read_wav_iq(args.file, n_samp)

    # Process
    print("\n[Process]")
    dop, dly, caf = process(iq, FS)

    # Plot
    print("\n[Plot]")
    plot_rd(dop, dly, caf, args.output)

    # Detections
    print("\n[Detections]")
    thresh = np.percentile(caf, 99.5)
    peaks = np.argwhere(caf > thresh)
    print(f"  Candidates: {len(peaks)}")
    for p_idx in peaks[:10]:
        di, ri = p_idx[0], p_idx[1]
        snr = 20 * np.log10(caf[di, ri] / np.median(caf) + 1e-10)
        print(f"  {dly[ri]:5.1f} km | {dop[di]:+.0f} Hz | SNR~{snr:.0f} dB")

    print(f"\nDone -> {args.output}")


if __name__ == "__main__":
    main()
