from __future__ import annotations

import warnings

import numpy as np
from scipy.ndimage import uniform_filter1d

with warnings.catch_warnings():
    warnings.simplefilter("ignore")
    import pyworld as pw


def clean_f0(f0: np.ndarray, frame_ms: float, min_run_ms: float = 30.0,
             max_gap_ms: float = 25.0) -> np.ndarray:
    f0 = f0.astype(np.float64).copy()
    voiced = f0 > 0
    if not voiced.any():
        return f0
    min_run = max(1, int(round(min_run_ms / frame_ms)))
    for a, b in _runs(voiced):
        if b - a < min_run:
            f0[a:b] = 0.0
    voiced = f0 > 0
    if not voiced.any():
        return f0
    idx = np.flatnonzero(voiced)
    lv = np.log2(f0[idx])
    win = max(3, int(round(120.0 / frame_ms)) | 1)
    from scipy.signal import medfilt
    ref = medfilt(lv, kernel_size=min(win, len(lv) if len(lv) % 2 else len(lv) - 1) or 1)
    d = lv - ref
    lv = np.where(d > 0.75, lv - 1.0, np.where(d < -0.75, lv + 1.0, lv))
    f0[idx] = 2.0 ** lv
    max_gap = int(round(max_gap_ms / frame_ms))
    for a, b in _runs(~voiced):
        if a > 0 and b < len(f0) and (b - a) <= max_gap:
            f0[a:b] = np.exp(np.linspace(np.log(f0[a - 1]), np.log(f0[b]), b - a + 2)[1:-1])
    return f0


def voicing_gate(f0: np.ndarray, ap: np.ndarray, sr: int, threshold: float = 0.5) -> np.ndarray:
    freqs = np.linspace(0, sr / 2, ap.shape[1])
    band = (freqs > 100) & (freqs < 1500)
    noisy = ap[:, band].mean(axis=1) > threshold
    out = f0.copy()
    out[noisy] = 0.0
    return out


def _runs(mask: np.ndarray):
    m = np.concatenate([[False], mask.astype(bool), [False]])
    d = np.diff(m.astype(np.int8))
    starts = np.flatnonzero(d == 1)
    ends = np.flatnonzero(d == -1)
    return list(zip(starts, ends))


def flat_target_f0(f0: np.ndarray, target_hz: float, frame_ms: float, accuracy: float = 1.0,
                   humanization: float = 0.0, max_cents: float = 15.0) -> tuple[np.ndarray, float]:
    voiced = f0 > 0
    out = np.zeros_like(f0)
    if not voiced.any():
        return out, 0.0
    lf = np.log2(f0[voiced])
    centre = float(np.median(lf))
    dev = np.zeros_like(f0)
    dev[voiced] = lf - centre
    keep = np.zeros_like(f0)
    if accuracy < 1.0 or humanization > 0.0:
        win = max(1, int(round(150.0 / frame_ms)))
        for a, b in _runs(voiced):
            seg = dev[a:b]
            slow = uniform_filter1d(seg, size=min(win, len(seg)), mode="nearest")
            fast = seg - slow
            keep[a:b] = (1.0 - accuracy) * slow + humanization * fast
        cap = max_cents / 1200.0
        keep = np.clip(keep, -cap, cap)
        keep[voiced] -= keep[voiced].mean()
    out[voiced] = target_hz * 2.0 ** keep[voiced]
    return out, float(2.0 ** centre)


def warp_envelope(sp: np.ndarray, alpha: float) -> np.ndarray:
    if abs(alpha - 1.0) < 1e-6:
        return sp
    bins = sp.shape[1]
    src = np.arange(bins) / alpha
    i0 = np.clip(np.floor(src).astype(int), 0, bins - 1)
    i1 = np.clip(i0 + 1, 0, bins - 1)
    w = np.clip(src - i0, 0.0, 1.0)
    log_sp = np.log(np.maximum(sp, 1e-16))
    out = log_sp[:, i0] * (1 - w) + log_sp[:, i1] * w
    return np.exp(out)


def stretch_frames(arr: np.ndarray, ratio: float, log_domain: bool = False) -> np.ndarray:
    T = arr.shape[0]
    new_t = max(2, int(round(T * ratio)))
    pos = np.linspace(0, T - 1, new_t)
    i0 = np.floor(pos).astype(int)
    i1 = np.minimum(i0 + 1, T - 1)
    w = pos - i0
    if arr.ndim == 1:
        a0, a1 = arr[i0], arr[i1]
        voiced = (a0 > 0) & (a1 > 0)
        lin = a0 * (1 - w) + a1 * w
        nearest = np.where(w < 0.5, a0, a1)
        return np.where(voiced, lin, nearest)
    w = w[:, None]
    if log_domain:
        la = np.log(np.maximum(arr, 1e-16))
        return np.exp(la[i0] * (1 - w) + la[i1] * w)
    return arr[i0] * (1 - w) + arr[i1] * w


def frames_to_samples(mask: np.ndarray, frame_ms: float, sr: int, n: int) -> np.ndarray:
    t_frames = np.arange(len(mask)) * frame_ms / 1000.0
    t_samples = np.arange(n) / sr
    return np.interp(t_samples, t_frames, mask.astype(np.float64))


def smooth_curve(curve: np.ndarray, sr: int, ms: float) -> np.ndarray:
    n = max(1, int(sr * ms / 1000))
    if n <= 1:
        return curve
    k = np.hanning(n + 2)[1:-1]
    k /= k.sum()
    return np.convolve(curve, k, mode="same")


def onset_frames(x: np.ndarray, sr: int, hop_ms: float = 5.0) -> np.ndarray:
    hop = max(1, int(sr * hop_ms / 1000))
    win = hop * 4
    if len(x) < win * 2:
        return np.array([0], dtype=int)
    frames = np.lib.stride_tricks.sliding_window_view(x, win)[::hop]
    spec = np.abs(np.fft.rfft(frames * np.hanning(win), axis=1))
    flux = np.maximum(np.diff(np.log1p(spec * 10), axis=0), 0).sum(axis=1)
    flux = np.concatenate([[0.0], flux])
    if flux.max() <= 0:
        return np.array([0], dtype=int)
    med = np.median(flux)
    mad = np.median(np.abs(flux - med)) + 1e-9
    thr = med + 6 * mad
    peaks = [i for i in range(1, len(flux) - 1)
             if flux[i] > thr and flux[i] >= flux[i - 1] and flux[i] >= flux[i + 1]]
    out, last = [], -10 ** 9
    min_dist = int(60 / hop_ms)
    for p in peaks:
        if p - last >= min_dist:
            out.append(p)
            last = p
    env = np.abs(x)
    first = int(np.argmax(env > env.max() * 0.05)) if env.max() > 0 else 0
    positions = sorted(set([first] + [p * hop for p in out]))
    return np.array(positions, dtype=int)


def transient_mask(n: int, sr: int, onsets: np.ndarray, window_ms: float) -> np.ndarray:
    m = np.zeros(n)
    hold = int(sr * 0.003)
    decay = max(1, int(sr * window_ms / 1000))
    shape = np.concatenate([np.ones(hold), 0.5 + 0.5 * np.cos(np.linspace(0, np.pi, decay))])
    for o in onsets:
        a = int(o)
        b = min(n, a + len(shape))
        if a < n:
            m[a:b] = np.maximum(m[a:b], shape[: b - a])
    return m
