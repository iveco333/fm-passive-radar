#!/usr/bin/env python3
"""
SDRplay API v3.07 ctypes wrapper for RSP1 on Windows.

Uses the installed sdrplay_api.dll directly.
Structured according to the official sdrplay_api.h v3.07 headers.
"""

import ctypes
from ctypes import (
    c_void_p, c_uint, c_uint16, c_short, c_ubyte, c_double,
    c_int, c_char, c_char_p, c_float,
    POINTER, Structure, CFUNCTYPE, byref,
)
import os
import numpy as np
import time
import weakref

# Ensure DLL path is findable
os.add_dll_directory(r"C:\Program Files\SDRplay\API\x64")

_API_DLL = None


def _dll():
    global _API_DLL
    if _API_DLL is not None:
        return _API_DLL
    paths = [
        r"C:\Program Files\SDRplay\API\x64\sdrplay_api.dll",
        r"C:\Program Files\SDRplay\API\x86\sdrplay_api.dll",
        r"C:\Windows\System32\sdrplay_api.dll",
    ]
    for p in paths:
        try:
            _API_DLL = ctypes.WinDLL(p)
            return _API_DLL
        except OSError:
            continue
    raise OSError("sdrplay_api.dll not found. Install from sdrplay.com/downloads")


# ---- C structs (from sdrplay_api.h v3.07) ----

SDRPLAY_MAX_SER_NO_LEN = 64


class sdrplay_api_GainValuesT(Structure):
    _fields_ = [("curr", c_float), ("max", c_float), ("min", c_float)]


class sdrplay_api_GainT(Structure):
    _fields_ = [
        ("gRdB",        c_int),
        ("LNAstate",    c_ubyte),
        ("syncUpdate",  c_ubyte),
        ("minGr",       c_int),  # enum
        ("gainVals",    sdrplay_api_GainValuesT),
    ]


class sdrplay_api_RfFreqT(Structure):
    _fields_ = [
        ("rfHz",        c_double),
        ("syncUpdate",  c_ubyte),
    ]


class sdrplay_api_DcOffsetTunerT(Structure):
    _fields_ = [
        ("dcCal",           c_ubyte),
        ("speedUp",         c_ubyte),
        ("trackTime",       c_int),
        ("refreshRateTime", c_int),
    ]


class sdrplay_api_TunerParamsT(Structure):
    _fields_ = [
        ("bwType",          c_int),  # enum sdrplay_api_Bw_MHzT
        ("ifType",          c_int),  # enum sdrplay_api_If_kHzT
        ("loMode",          c_int),  # enum sdrplay_api_LoModeT
        ("gain",            sdrplay_api_GainT),
        ("rfFreq",          sdrplay_api_RfFreqT),
        ("dcOffsetTuner",   sdrplay_api_DcOffsetTunerT),
    ]


class sdrplay_api_DcOffsetT(Structure):
    _fields_ = [("DCenable", c_ubyte), ("IQenable", c_ubyte)]


class sdrplay_api_DecimationT(Structure):
    _fields_ = [
        ("enable",           c_ubyte),
        ("decimationFactor", c_ubyte),
        ("wideBandSignal",   c_ubyte),
    ]


class sdrplay_api_AgcT(Structure):
    _fields_ = [
        ("enable",             c_int),
        ("setPoint_dBfs",      c_int),
        ("attack_ms",          c_uint16),
        ("decay_ms",           c_uint16),
        ("decay_delay_ms",     c_uint16),
        ("decay_threshold_dB", c_uint16),
        ("syncUpdate",         c_int),
    ]


class sdrplay_api_ControlParamsT(Structure):
    _fields_ = [
        ("dcOffset",    sdrplay_api_DcOffsetT),
        ("decimation",  sdrplay_api_DecimationT),
        ("agc",         sdrplay_api_AgcT),
        ("adsbMode",    c_int),
    ]


class sdrplay_api_Rsp1aTunerParamsT(Structure):
    _fields_ = [
        ("biasTEnable", c_ubyte),
        ("rfNotchEnable", c_ubyte),
        ("rfDabNotchEnable", c_ubyte),
    ]


# Stubs for unused RSP-specific params
class sdrplay_api_Rsp2TunerParamsT(Structure):
    _fields_ = [("dummy", c_ubyte)]


class sdrplay_api_RspDuoTunerParamsT(Structure):
    _fields_ = [("dummy", c_ubyte)]


class sdrplay_api_RspDxTunerParamsT(Structure):
    _fields_ = [("dummy", c_ubyte)]


class sdrplay_api_RxChannelParamsT(Structure):
    _fields_ = [
        ("tunerParams",        sdrplay_api_TunerParamsT),
        ("ctrlParams",         sdrplay_api_ControlParamsT),
        ("rsp1aTunerParams",   sdrplay_api_Rsp1aTunerParamsT),
        ("rsp2TunerParams",    sdrplay_api_Rsp2TunerParamsT),
        ("rspDuoTunerParams",  sdrplay_api_RspDuoTunerParamsT),
        ("rspDxTunerParams",   sdrplay_api_RspDxTunerParamsT),
    ]


class sdrplay_api_DeviceT(Structure):
    _fields_ = [
        ("SerNo",           c_char * SDRPLAY_MAX_SER_NO_LEN),
        ("hwVer",           c_ubyte),
        ("tuner",           c_int),
        ("rspDuoMode",      c_int),
        ("rspDuoSampleFreq", c_double),
        ("dev",             c_void_p),
    ]


class sdrplay_api_DeviceParamsT(Structure):
    _fields_ = [
        ("devParams",    c_void_p),
        ("rxChannelA",   POINTER(sdrplay_api_RxChannelParamsT)),
        ("rxChannelB",   POINTER(sdrplay_api_RxChannelParamsT)),
    ]


# Stream callback params (v3.07 signature)
class sdrplay_api_StreamCbParamsT(Structure):
    _fields_ = [
        ("firstSampleNum", c_uint),
        ("grChanged",      c_int),
        ("rfChanged",      c_int),
        ("fsChanged",      c_int),
        ("numSamples",     c_uint),
    ]


# Event callback params
class sdrplay_api_GainCbParamT(Structure):
    _fields_ = [
        ("gRdB",      c_uint),
        ("lnaGRdB",   c_uint),
        ("currGain",  c_double),
    ]


class sdrplay_api_PowerOverloadCbParamT(Structure):
    _fields_ = [("powerOverloadChangeType", c_int)]


class sdrplay_api_RspDuoModeCbParamT(Structure):
    _fields_ = [("modeChangeType", c_int)]


class sdrplay_api_EventParamsT(Structure):
    _fields_ = [
        ("gainParams",          sdrplay_api_GainCbParamT),
        ("powerOverloadParams", sdrplay_api_PowerOverloadCbParamT),
        ("rspDuoModeParams",    sdrplay_api_RspDuoModeCbParamT),
    ]


# Callback types (v3.07)
STREAM_CB = CFUNCTYPE(
    None,
    POINTER(c_short),                   # xi
    POINTER(c_short),                   # xq
    POINTER(sdrplay_api_StreamCbParamsT),  # params
    c_uint,                             # numSamples
    c_uint,                             # reset
    c_void_p,                           # cbContext
)

EVENT_CB = CFUNCTYPE(
    None,
    c_int,                              # eventId
    c_int,                              # tuner
    POINTER(sdrplay_api_EventParamsT),  # params
    c_void_p,                           # cbContext
)


class sdrplay_api_CallbackFnsT(Structure):
    _fields_ = [
        ("StreamACbFn", STREAM_CB),
        ("StreamBCbFn", STREAM_CB),
        ("EventCbFn",   EVENT_CB),
    ]


# ---- Constants ----

# Bandwidth
BW_0_200 = 200
BW_0_300 = 300
BW_0_600 = 600
BW_1_536 = 1536
BW_5_000 = 5000
BW_6_000 = 6000
BW_7_000 = 7000
BW_8_000 = 8000

# IF type
IF_Zero = 0
IF_0_450 = 450
IF_1_620 = 1620
IF_2_048 = 2048

# LO mode
LO_Auto = 1

# Min GR
NORMAL_MIN_GR = 20

# Tuner select
TUNER_A = 1
TUNER_B = 2

# Update reasons
UPDATE_DEV_FS          = 0x00000001
UPDATE_DEV_PPM         = 0x00000002
UPDATE_TUNER_GR        = 0x00008000
UPDATE_TUNER_FRF       = 0x00020000
UPDATE_TUNER_BWTYPE    = 0x00040000
UPDATE_TUNER_IFTYPE    = 0x00080000
UPDATE_TUNER_DCOFFSET  = 0x00100000
UPDATE_TUNER_LOMODE    = 0x00200000
UPDATE_CTRL_DC_IQ      = 0x00400000
UPDATE_CTRL_DECIMATION = 0x00800000
UPDATE_CTRL_AGC        = 0x01000000

# AGC modes
AGC_DISABLE = 0
AGC_100HZ = 1
AGC_50HZ = 2
AGC_5HZ = 3
AGC_CTRL_EN = 4


# ---- Python API ----

# Static no-op callbacks to prevent GC
_NOOP_STREAM_CB = STREAM_CB(lambda xi, xq, p, n, r, ctx: None)
_NOOP_EVENT_CB = EVENT_CB(lambda e, t, p, ctx: None)


class SDRplayAPI:
    """SDRplay API v3.07 Python wrapper for RSP1."""

    def __init__(self):
        self.api = _dll()
        self._bind()
        self.device = None
        self.params = None
        self._inited = False
        self._sample_rate = 0.0
        self._stream_cb = None
        self._stream_buf = None
        self._stream_done = False
        self._open()

    def _bind(self):
        a = self.api
        self._Open = self._fn(a, "sdrplay_api_Open", [], c_int)
        self._Close = self._fn(a, "sdrplay_api_Close", [], c_int)
        self._GetDevices = self._fn(
            a, "sdrplay_api_GetDevices",
            [POINTER(sdrplay_api_DeviceT), POINTER(c_uint), c_uint], c_int,
        )
        self._SelectDevice = self._fn(
            a, "sdrplay_api_SelectDevice", [POINTER(sdrplay_api_DeviceT)], c_int,
        )
        self._ReleaseDevice = self._fn(
            a, "sdrplay_api_ReleaseDevice", [POINTER(sdrplay_api_DeviceT)], c_int,
        )
        self._GetErrorString = self._fn(
            a, "sdrplay_api_GetErrorString", [c_int], c_char_p,
        )
        self._GetDeviceParams = self._fn(
            a, "sdrplay_api_GetDeviceParams",
            [c_void_p, POINTER(POINTER(sdrplay_api_DeviceParamsT))], c_int,
        )
        self._Init = self._fn(
            a, "sdrplay_api_Init",
            [c_void_p, POINTER(sdrplay_api_CallbackFnsT), c_void_p], c_int,
        )
        self._Uninit = self._fn(
            a, "sdrplay_api_Uninit", [c_void_p], c_int,
        )
        self._Update = self._fn(
            a, "sdrplay_api_Update",
            [c_void_p, c_int, c_int, c_int], c_int,
        )
        self._DebugEnable = self._fn(
            a, "sdrplay_api_DebugEnable", [c_void_p, c_int], c_int,
        )

    def _fn(self, a, name, argtypes, restype):
        f = getattr(a, name)
        f.argtypes = argtypes
        f.restype = restype
        return f

    def _check(self, ret, ctx=""):
        if ret != 0:
            msg = self._GetErrorString(ret).decode()
            raise RuntimeError(f"SDRplay API error ({ret}){': ' + ctx if ctx else ''}: {msg}")

    def _open(self):
        self._check(self._Open())

    def select_device(self, index=0):
        devs = (sdrplay_api_DeviceT * 16)()
        count = c_uint(0)
        self._check(self._GetDevices(devs, byref(count), 16))
        if count.value == 0:
            raise RuntimeError("No SDRplay device found. Plug in RSP1?")
        if index >= count.value:
            raise RuntimeError(f"Device index {index} >= {count.value}")
        self.device = devs[index]
        hw = self.device.hwVer
        names = {1: "RSP1", 255: "RSP1A", 2: "RSP2", 3: "RSPduo", 4: "RSPdx"}
        print(f"  Device: {names.get(hw, f'Unknown(hwVer={hw})')}  SN: {self.device.SerNo.decode()}")
        self._check(self._SelectDevice(byref(self.device)),
                    f"SelectDevice hwVer={hw}")
        pptr = POINTER(sdrplay_api_DeviceParamsT)()
        self._check(self._GetDeviceParams(self.device.dev, byref(pptr)))
        self.params = pptr.contents
        return self.device

    @property
    def ch(self):
        """Shortcut to rxChannelA"""
        return self.params.rxChannelA.contents

    def set_frequency(self, freq_hz):
        ch = self.ch
        ch.tunerParams.rfFreq.rfHz = freq_hz
        ch.tunerParams.rfFreq.syncUpdate = 1
        print(f"  Freq: {freq_hz/1e6:.2f} MHz")

    def set_sample_rate(self, rate):
        """Set sample rate via bandwidth selection (RSP1: no decimation)."""
        self._sample_rate = rate
        ch = self.ch
        ch.ctrlParams.decimation.enable = 0
        ch.tunerParams.ifType = IF_Zero
        if rate <= 0.3e6:
            ch.tunerParams.bwType = BW_0_200
        elif rate <= 0.6e6:
            ch.tunerParams.bwType = BW_0_300
        elif rate <= 1.6e6:
            ch.tunerParams.bwType = BW_0_600
        elif rate <= 6e6:
            ch.tunerParams.bwType = BW_1_536  # gives ~1.94 MSPS
        elif rate <= 8e6:
            ch.tunerParams.bwType = BW_6_000
        else:
            raise ValueError(f"Unsupported rate: {rate}")
        print(f"  Sample rate: {rate/1e6:.2f} MHz (actual: ~{rate/1e6:.2f} depending on BW)")

    def set_gain(self, gain_db):
        ch = self.ch
        if gain_db == "auto":
            ch.ctrlParams.agc.enable = AGC_50HZ
            print("  Gain: AGC")
            return
        g = max(20, min(59, int(gain_db)))
        ch.tunerParams.gain.gRdB = g
        ch.tunerParams.gain.minGr = NORMAL_MIN_GR
        ch.tunerParams.gain.syncUpdate = 0  # Don't sync before Init
        print(f"  Gain: {gain_db} dB (gRdB={g})")

    def _apply_update(self, reason):
        """Call Update (only valid after Init)."""
        if self._inited:
            self._check(
                self._Update(self.device.dev, TUNER_A, reason, 0),
            )

    # After Init, updates go through this
    def set_frequency_live(self, freq_hz):
        self.set_frequency(freq_hz)
        self._apply_update(UPDATE_TUNER_FRF)

    def set_gain_live(self, gain_db):
        self.set_gain(gain_db)
        self._apply_update(UPDATE_TUNER_GR)

    def set_sample_rate_live(self, rate):
        self.set_sample_rate(rate)
        self._apply_update(UPDATE_TUNER_BWTYPE | UPDATE_TUNER_IFTYPE | UPDATE_CTRL_DECIMATION)

    def _make_cb(self):
        ref = weakref.ref(self)

        def cb(xi, xq, params_ptr, num_samps, reset, ctx):
            self = ref()
            if self is None or self._stream_done:
                return
            n = num_samps
            if n == 0:
                return
            xi_np = np.empty(n, dtype=np.int16)
            xq_np = np.empty(n, dtype=np.int16)
            ctypes.memmove(xi_np.ctypes.data, xi, n * 2)
            ctypes.memmove(xq_np.ctypes.data, xq, n * 2)
            iq = np.empty(n, dtype=np.complex64)
            iq.real = xi_np.astype(np.float32)
            iq.imag = xq_np.astype(np.float32)
            iq /= 32768.0
            if self._stream_buf is not None:
                self._stream_buf.extend(iq.tobytes())

        return STREAM_CB(cb)

    def capture(self, time_seconds):
        n = int(self._sample_rate * time_seconds)
        return self.capture_samples(n)

    def capture_samples(self, n_samples):
        self._stream_buf = bytearray()
        self._stream_done = False
        self._stream_cb = self._make_cb()

        cb_fns = sdrplay_api_CallbackFnsT()
        cb_fns.StreamACbFn = self._stream_cb
        cb_fns.StreamBCbFn = _NOOP_STREAM_CB
        cb_fns.EventCbFn = _NOOP_EVENT_CB

        self._check(self._Init(self.device.dev, byref(cb_fns), c_void_p(0)), "Init")
        self._inited = True

        target = n_samples * 8
        timeout = max(30.0, n_samples / self._sample_rate * 2)

        t0 = time.time()
        while len(self._stream_buf) < target:
            if time.time() - t0 > timeout:
                break
            time.sleep(0.005)

        self._stream_done = True
        self._check(self._Uninit(self.device.dev), "Uninit")
        self._inited = False
        self._stream_cb = None

        n_actual = len(self._stream_buf) // 8
        iq = np.frombuffer(self._stream_buf[:n_actual * 8], dtype=np.complex64)
        if len(iq) > n_samples:
            iq = iq[:n_samples]
        print(f"  Captured: {len(iq)} samples ({len(iq)/self._sample_rate:.2f}s)")
        return iq

    def capture_continuous(self, time_seconds):
        """连续采集（只Init一次，不Uninit，适合扫频）"""
        n = int(self._sample_rate * time_seconds)
        if not self._inited:
            self._stream_buf = bytearray()
            self._stream_done = False
            self._stream_cb = self._make_cb()
            cb_fns = sdrplay_api_CallbackFnsT()
            cb_fns.StreamACbFn = self._stream_cb
            cb_fns.StreamBCbFn = _NOOP_STREAM_CB
            cb_fns.EventCbFn = _NOOP_EVENT_CB
            self._check(self._Init(self.device.dev, byref(cb_fns), c_void_p(0)), "Init")
            self._inited = True

        # Uninit前先确保流停止
        self._stream_done = True
        time.sleep(0.01)
        self._stream_cb = None

        # 重新Init开始新采集
        self._check(self._Uninit(self.device.dev), "Uninit")
        self._inited = False

        self._stream_buf = bytearray()
        self._stream_done = False
        self._stream_cb = self._make_cb()
        cb_fns = sdrplay_api_CallbackFnsT()
        cb_fns.StreamACbFn = self._stream_cb
        cb_fns.StreamBCbFn = _NOOP_STREAM_CB
        cb_fns.EventCbFn = _NOOP_EVENT_CB
        self._check(self._Init(self.device.dev, byref(cb_fns), c_void_p(0)), "Init")
        self._inited = True

        target = n * 8
        timeout = max(10.0, n / self._sample_rate * 2)
        t0 = time.time()
        while len(self._stream_buf) < target:
            if time.time() - t0 > timeout:
                break
            time.sleep(0.005)

        self._stream_done = True
        n_actual = len(self._stream_buf) // 8
        iq = np.frombuffer(self._stream_buf[:n_actual * 8], dtype=np.complex64)
        if len(iq) > n:
            iq = iq[:n]
        return iq

    def close(self):
        try:
            if self._inited:
                self._Uninit(self.device.dev)
        except Exception:
            pass
        try:
            if self.device is not None:
                self._ReleaseDevice(byref(self.device))
        except Exception:
            pass
        try:
            self._Close()
        except Exception:
            pass

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()
