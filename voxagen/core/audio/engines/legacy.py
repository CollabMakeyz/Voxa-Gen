from __future__ import annotations

import numpy as np

from ....models.config import LegacyParams
from ..dsp import as_2d
from .base import Engine, EngineOutput, params_key

LEGACY_CHAIN_VERSION = 1


class LegacyEngine(Engine):
    id = "legacy"
    resampling_quality = "hq"

    def __init__(self, params: LegacyParams):
        self.p = params

    @property
    def keeps_channels(self) -> bool:
        return False

    def analysis_key(self) -> str:
        return f"legacy|v{LEGACY_CHAIN_VERSION}|{self.p.internal_rate}"

    def render_key(self) -> str:
        return f"legacy|v{LEGACY_CHAIN_VERSION}|" + params_key(self.p)

    def analyze(self, x: np.ndarray, sr: int):
        import parselmouth
        from parselmouth.praat import call
        mono = as_2d(x).astype(np.float64).mean(axis=1)
        snd = parselmouth.Sound(mono, sampling_frequency=float(sr))
        if int(sr) != self.p.internal_rate:
            snd = call(snd, "Resample", float(self.p.internal_rate), 1)
        return snd

    def render(self, snd, x: np.ndarray, sr: int, target_hz: float, duration_ratio: float = 1.0) -> EngineOutput:
        from parselmouth.praat import call
        p = self.p
        warnings = []
        manip = call(snd, "To Manipulation", p.time_step, p.pitch_floor, p.pitch_ceiling)
        tier = call(manip, "Extract pitch tier")
        n_points = call(tier, "Get number of points")
        if n_points == 0:
            warnings.append("No voiced content detected; sample kept at its original pitch.")
            out = snd
        else:
            call(tier, "Formula", f"{target_hz}")
            call([tier, manip], "Replace pitch tier")
            out = call(manip, "Get resynthesis (overlap-add)")
        if abs(duration_ratio - 1.0) > 1e-3:
            out = call(out, "Lengthen (overlap-add)", max(p.pitch_floor, 75.0), min(p.pitch_ceiling, 600.0),
                       float(duration_ratio))
        y = np.asarray(out.values, dtype=np.float64)[0]
        return EngineOutput(y[:, None], int(p.internal_rate), warnings, {"chain_version": LEGACY_CHAIN_VERSION})
