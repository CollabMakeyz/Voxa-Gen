from __future__ import annotations

import numpy as np

from ..audio.dsp import to_mono
from ..samples.library import PitchInfo
from .tuning import describe_hz

MIN_VOICED_RATIO = 0.25
MAX_SPREAD_CENTS = 120.0


def pitch_track(x: np.ndarray, sr: int, floor: float = 50.0, ceiling: float = 1100.0,
                time_step: float = 0.01) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    import parselmouth
    mono = to_mono(x)[:, 0]
    snd = parselmouth.Sound(mono.astype(np.float64), sampling_frequency=float(sr))
    p = snd.to_pitch_ac(time_step=time_step, pitch_floor=floor, pitch_ceiling=ceiling,
                        very_accurate=True)
    f0 = p.selected_array["frequency"]
    strength = p.selected_array["strength"]
    return p.xs(), f0, strength


def detect_pitch(x: np.ndarray, sr: int, a4_hz: float = 440.0) -> PitchInfo:
    info = PitchInfo()
    if len(x) < sr * 0.03:
        info.reason = "Sample too short for pitch analysis"
        return info
    try:
        _, f0, strength = pitch_track(x, sr)
    except Exception as exc:
        info.reason = f"Pitch analysis failed: {exc}"
        return info
    voiced = f0 > 0
    total = len(f0)
    info.voiced_ratio = float(voiced.sum()) / total if total else 0.0
    if voiced.sum() < 3:
        info.reason = "No stable voiced content detected"
        return info
    v = f0[voiced]
    med = float(np.median(v))
    cents = 1200.0 * np.log2(v / med)
    q75, q25 = np.percentile(cents, [75, 25])
    info.spread_cents = float(q75 - q25)
    info.median_hz = med
    info.note, info.cents = describe_hz(med, a4_hz)
    s = float(np.median(strength[voiced]))
    ratio_score = min(1.0, info.voiced_ratio / 0.6)
    spread_score = max(0.0, 1.0 - info.spread_cents / (2 * MAX_SPREAD_CENTS))
    info.confidence = round(float(ratio_score * spread_score * min(1.0, s / 0.7)), 3)
    if info.voiced_ratio < MIN_VOICED_RATIO:
        info.reason = f"Only {info.voiced_ratio:.0%} of the sample is voiced"
    elif info.spread_cents > MAX_SPREAD_CENTS:
        info.reason = f"Pitch is unstable (spread {info.spread_cents:.0f} cents)"
    else:
        info.reliable = True
    return info


def median_f0(x: np.ndarray, sr: int, skip_edges: float = 0.15, floor=40.0, ceiling=1600.0) -> float:
    _, f0, _ = pitch_track(x, sr, floor, ceiling, time_step=0.005)
    n = len(f0)
    a, b = int(n * skip_edges), int(n * (1 - skip_edges))
    seg = f0[a:b]
    seg = seg[seg > 0]
    return float(np.median(seg)) if seg.size else 0.0
