from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from ....models.config import RobotParams
from ..dsp import active_rms, as_2d, db_to_gain
from .base import Engine, EngineOutput, params_key
from .world_utils import clean_f0, flat_target_f0, pw, stretch_frames, voicing_gate


@dataclass
class RobotAnalysis:
    f0: np.ndarray
    sp: np.ndarray
    ap: np.ndarray
    frame_ms: float
    channel_gains: np.ndarray


class RobotEngine(Engine):
    id = "robot"

    def __init__(self, params: RobotParams):
        self.p = params
        self.resampling_quality = params.resampling_quality

    def analysis_key(self) -> str:
        return f"robot|{self.p.frame_period_ms}"

    def render_key(self) -> str:
        return "robot|" + params_key(self.p)

    def analyze(self, x: np.ndarray, sr: int) -> RobotAnalysis:
        x = as_2d(x).astype(np.float64)
        mid = np.ascontiguousarray(x.mean(axis=1))
        fms = float(self.p.frame_period_ms)
        f0, t = pw.dio(mid, sr, f0_floor=50.0, f0_ceil=1100.0, frame_period=fms)
        f0 = pw.stonemask(mid, f0, t, sr)
        f0 = clean_f0(f0, fms, min_run_ms=40.0, max_gap_ms=30.0)
        ap = pw.d4c(mid, f0, t, sr)
        f0 = clean_f0(voicing_gate(f0, ap, sr), fms, min_run_ms=40.0, max_gap_ms=30.0)
        sp = pw.cheaptrick(mid, f0, t, sr)
        m_rms = np.sqrt(np.mean(mid ** 2)) + 1e-12
        gains = np.sqrt(np.mean(x ** 2, axis=0)) / m_rms
        return RobotAnalysis(f0, sp, ap, fms, gains)

    def render(self, a: RobotAnalysis, x: np.ndarray, sr: int, target_hz: float,
               duration_ratio: float = 1.0) -> EngineOutput:
        x = as_2d(x).astype(np.float64)
        n_out = int(round(len(x) * duration_ratio))
        if not (a.f0 > 0).any():
            return EngineOutput(x.copy(), sr, ["No voiced content detected; sample kept at its original pitch."],
                                {"source_hz": 0.0})
        f0, centre = flat_target_f0(a.f0, target_hz, a.frame_ms)
        sp, ap = a.sp, a.ap
        if abs(duration_ratio - 1.0) > 1e-3:
            f0 = stretch_frames(f0, duration_ratio)
            sp = stretch_frames(sp, duration_ratio, log_domain=True)
            ap = stretch_frames(ap, duration_ratio)
        y = pw.synthesize(f0, np.ascontiguousarray(sp), np.ascontiguousarray(ap), sr, a.frame_ms)
        y = y[:n_out] if len(y) >= n_out else np.concatenate([y, np.zeros(n_out - len(y))])
        out = y[:, None] * a.channel_gains[None, :]
        if self.p.gain_compensation:
            r_in, r_out = active_rms(x, sr), active_rms(out, sr)
            if r_in > 0 and r_out > 0:
                out *= np.clip(r_in / r_out, db_to_gain(-12), db_to_gain(12))
        return EngineOutput(out, sr, [], {"source_hz": centre, "shift_semitones": 12 * np.log2(target_hz / centre)})
