from __future__ import annotations

import numpy as np
import soundfile as sf

try:
    import soxr
except ImportError:
    soxr = None

RESAMPLE_QUALITIES = ("lq", "mq", "hq", "vhq")


def load_audio(path: str) -> tuple[np.ndarray, int]:
    data, sr = sf.read(path, dtype="float64", always_2d=True)
    return data, int(sr)


def as_2d(x: np.ndarray) -> np.ndarray:
    return x[:, None] if x.ndim == 1 else x


def to_mono(x: np.ndarray) -> np.ndarray:
    x = as_2d(x)
    return x.mean(axis=1, keepdims=True) if x.shape[1] > 1 else x


def conform_channels(x: np.ndarray, channels: int) -> np.ndarray:
    x = as_2d(x)
    if x.shape[1] == channels:
        return x
    if channels == 1:
        return to_mono(x)
    if x.shape[1] == 1:
        return np.repeat(x, channels, axis=1)
    left = x[:, 0::2].mean(axis=1)
    right = x[:, 1::2].mean(axis=1)
    return np.stack([left, right], axis=1)


def resample(x: np.ndarray, sr_in: int, sr_out: int, quality: str = "vhq") -> np.ndarray:
    x = as_2d(x)
    if sr_in == sr_out or len(x) == 0:
        return x.copy()
    if soxr is not None:
        q = {"lq": "LQ", "mq": "MQ", "hq": "HQ", "vhq": "VHQ"}.get(quality, "VHQ")
        y = soxr.resample(np.ascontiguousarray(x, dtype=np.float64), sr_in, sr_out, quality=q)
        return as_2d(y)
    from math import gcd
    from scipy.signal import resample_poly
    g = gcd(sr_in, sr_out)
    return as_2d(resample_poly(x, sr_out // g, sr_in // g, axis=0))


def db_to_gain(db: float) -> float:
    return float(10.0 ** (db / 20.0))


def gain_to_db(g: float) -> float:
    return float(20.0 * np.log10(max(g, 1e-12)))


def peak(x: np.ndarray) -> float:
    return float(np.max(np.abs(x))) if x.size else 0.0


def active_rms(x: np.ndarray, sr: int, threshold_db: float = -45.0, frame_ms: float = 20.0) -> float:
    m = to_mono(x)[:, 0]
    n = max(1, int(sr * frame_ms / 1000))
    frames = len(m) // n
    if frames == 0:
        return float(np.sqrt(np.mean(m ** 2))) if len(m) else 0.0
    f = m[: frames * n].reshape(frames, n)
    rms = np.sqrt(np.mean(f ** 2, axis=1))
    top = rms.max()
    if top <= 0:
        return 0.0
    sel = rms[rms >= top * db_to_gain(threshold_db)]
    return float(np.sqrt(np.mean(sel ** 2)))


def apply_fades(x: np.ndarray, sr: int, fade_in_ms: float, fade_out_ms: float) -> np.ndarray:
    x = as_2d(x).copy()
    n = len(x)
    fi = min(int(round(sr * max(fade_in_ms, 0) / 1000)), n)
    fo = min(int(round(sr * max(fade_out_ms, 0) / 1000)), n)
    if fi + fo > n and fi + fo > 0:
        scale = n / float(fi + fo)
        fi, fo = int(fi * scale), int(fo * scale)
    if fi > 0:
        x[:fi] *= (0.5 - 0.5 * np.cos(np.linspace(0, np.pi, fi)))[:, None]
    if fo > 0:
        x[n - fo:] *= (0.5 + 0.5 * np.cos(np.linspace(0, np.pi, fo)))[:, None]
    return x


def trim_silence(x: np.ndarray, sr: int, threshold_db: float = -50.0, pad_ms: float = 10.0) -> np.ndarray:
    x = as_2d(x)
    if len(x) == 0:
        return x
    env = np.max(np.abs(x), axis=1)
    thr = db_to_gain(threshold_db)
    idx = np.flatnonzero(env > thr)
    if idx.size == 0:
        return x[:0]
    pad = int(sr * pad_ms / 1000)
    a = max(0, idx[0] - pad)
    b = min(len(x), idx[-1] + 1 + pad)
    return x[a:b]


def fit_length(x: np.ndarray, frames: int, mode: str, sr: int, release_ms: float = 8.0) -> tuple[np.ndarray, bool]:
    x = as_2d(x)
    n = len(x)
    if frames <= 0:
        return x, False
    if n < frames:
        return np.concatenate([x, np.zeros((frames - n, x.shape[1]))], axis=0), False
    if n > frames and mode in ("pad_trim", "stretch"):
        y = x[:frames].copy()
        r = min(frames, int(sr * release_ms / 1000))
        if r > 0 and mode == "pad_trim":
            y[frames - r:] *= np.linspace(1.0, 0.0, r)[:, None]
        return y, mode == "pad_trim"
    return x, False


def silence(frames: int, channels: int) -> np.ndarray:
    return np.zeros((max(frames, 0), channels))


def quantize(x: np.ndarray, bit_depth: str, dither: bool, rng: np.random.Generator | None = None) -> np.ndarray:
    x = as_2d(x)
    if bit_depth == "float32":
        return x.astype("<f4")
    if bit_depth == "pcm16":
        scale, lo, hi, dt = 32767.0, -32768, 32767, "<i2"
    elif bit_depth == "pcm24":
        scale, lo, hi, dt = 8388607.0, -8388608, 8388607, "<i4"
    else:
        raise ValueError(f"Unsupported bit depth: {bit_depth}")
    y = x * scale
    if dither and bit_depth == "pcm16":
        rng = rng or np.random.default_rng()
        y = y + (rng.random(y.shape) - rng.random(y.shape))
    return np.clip(np.round(y), lo, hi).astype(dt)
