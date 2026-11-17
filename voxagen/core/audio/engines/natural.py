from __future__ import annotations

import threading
from dataclasses import dataclass

import numpy as np
from scipy.ndimage import gaussian_filter1d, median_filter

from ....models.config import NaturalParams
from ..dsp import active_rms, as_2d, db_to_gain
from .base import Engine, EngineOutput, params_key
from .world_utils import (
    clean_f0, flat_target_f0, frames_to_samples, onset_frames, pw, smooth_curve,
    stretch_frames, transient_mask, voicing_gate, warp_envelope,
)

FRAME_MS = {"standard": 5.0, "high": 2.5, "ultra": 1.0}


@dataclass
class NaturalAnalysis:
    f0: np.ndarray
    sp: list
    ap: list
    frame_ms: float
    onsets: np.ndarray
    voiced_ratio: float
    source_hz: float


class NaturalEngine(Engine):
    def __init__(self, params: NaturalParams, engine_id: str = "natural"):
        self.p = params.effective()
        self.pitch_correction = params.tool_on("pitch_correction")
        self.id = engine_id
        self.resampling_quality = params.resampling_quality
        self._refined: dict[tuple, tuple] = {}
        self._refine_lock = threading.Lock()

    def analysis_key(self) -> str:
        p = self.p
        rng = "auto" if p.auto else f"{p.f0_floor}-{p.f0_ceil}"
        return f"natural|{p.quality}|{rng}"

    def render_key(self) -> str:
        return f"natural|pc={self.pitch_correction}|" + params_key(self.p)

    def _range(self) -> tuple[float, float]:
        return (40.0, 1100.0) if self.p.auto else (float(self.p.f0_floor), float(self.p.f0_ceil))

    def analyze(self, x: np.ndarray, sr: int) -> NaturalAnalysis:
        x = as_2d(x).astype(np.float64)
        mid = np.ascontiguousarray(x.mean(axis=1))
        fms = FRAME_MS.get(self.p.quality, 2.5)
        floor, ceil = self._range()
        f0, t = pw.harvest(mid, sr, f0_floor=floor, f0_ceil=ceil, frame_period=fms)
        f0 = pw.stonemask(mid, f0, t, sr)
        f0 = clean_f0(f0, fms)
        fft = pw.get_cheaptrick_fft_size(sr, floor)
        mid_ap = pw.d4c(mid, f0, t, sr, fft_size=fft)
        f0 = clean_f0(voicing_gate(f0, mid_ap, sr), fms)
        sp, ap = [], []
        for c in range(x.shape[1]):
            ch = np.ascontiguousarray(x[:, c])
            sp.append(pw.cheaptrick(ch, f0, t, sr, f0_floor=floor, fft_size=fft))
            ap.append(mid_ap if x.shape[1] == 1 else pw.d4c(ch, f0, t, sr, fft_size=fft))
        voiced = f0 > 0
        src = float(2 ** np.median(np.log2(f0[voiced]))) if voiced.any() else 0.0
        return NaturalAnalysis(f0=f0, sp=sp, ap=ap, frame_ms=fms, onsets=onset_frames(mid, sr),
                               voiced_ratio=float(voiced.mean()) if len(f0) else 0.0, source_hz=src)

    def render(self, a: NaturalAnalysis, x: np.ndarray, sr: int, target_hz: float,
               duration_ratio: float = 1.0) -> EngineOutput:
        p = self.p
        x = as_2d(x).astype(np.float64)
        n_out = int(round(len(x) * duration_ratio))
        if not (a.f0 > 0).any():
            return EngineOutput(x.copy(), sr, ["No voiced content detected; sample kept at its original pitch."],
                                {"source_hz": 0.0, "voiced_ratio": 0.0})

        if not self.pitch_correction:
            target_hz = a.source_hz
        new_f0, centre = flat_target_f0(a.f0, target_hz, a.frame_ms, p.pitch_accuracy,
                                        p.humanization, p.humanization_max_cents)
        ratio = target_hz / centre
        alpha = ratio ** (1.0 - float(np.clip(p.formant_preservation, 0, 1)))
        stretched = abs(duration_ratio - 1.0) > 1e-3
        voiced = a.f0 > 0

        refined_needed = p.wet > 0.0
        plain_needed = p.wet < 1.0
        refined = np.zeros((n_out, x.shape[1]))
        plain = np.zeros((n_out, x.shape[1])) if plain_needed else None

        f0_syn = stretch_frames(new_f0, duration_ratio) if stretched else new_f0
        for c in range(x.shape[1]):
            sp = warp_envelope(a.sp[c], alpha)
            ap = a.ap[c]
            if plain_needed:
                y = self._synth(f0_syn, sp, ap, sr, a.frame_ms, duration_ratio, n_out)
                plain[:, c] = y
            if refined_needed:
                sp_r, ap_r = self._refine_cached(a, c, sp, ap, sr, voiced)
                refined[:, c] = self._synth(f0_syn, sp_r, ap_r, sr, a.frame_ms, duration_ratio, n_out)

        out = refined
        warnings = []
        if not stretched and refined_needed:
            out = self._hybrid(out, x, sr, a)
        elif stretched and (p.vuv_processing or p.transient_preservation > 0):
            warnings.append("Time-stretch active: original-signal blending (V/UV, transients) disabled.")
        if plain_needed:
            out = p.wet * out + (1.0 - p.wet) * plain

        if p.gain_compensation:
            r_in, r_out = active_rms(x, sr), active_rms(out, sr)
            if r_in > 0 and r_out > 0:
                g = np.clip(r_in / r_out, db_to_gain(-12), db_to_gain(12))
                out = out * g
        info = {"source_hz": centre, "shift_semitones": 12 * np.log2(ratio),
                "voiced_ratio": a.voiced_ratio, "formant_alpha": alpha}
        if abs(12 * np.log2(ratio)) > 24:
            warnings.append(f"Large shift ({12 * np.log2(ratio):+.1f} st); artifacts are more likely.")
        return EngineOutput(out, sr, warnings, info)

    def _synth(self, f0, sp, ap, sr, fms, ratio, n_out) -> np.ndarray:
        if abs(ratio - 1.0) > 1e-3:
            sp = stretch_frames(sp, ratio, log_domain=True)
            ap = stretch_frames(ap, ratio)
        y = pw.synthesize(np.ascontiguousarray(f0), np.ascontiguousarray(sp),
                          np.ascontiguousarray(ap), sr, fms)
        if len(y) >= n_out:
            return y[:n_out]
        return np.concatenate([y, np.zeros(n_out - len(y))])

    def _refine_cached(self, a: NaturalAnalysis, c: int, sp, ap, sr, voiced):
        if sp is not a.sp[c]:
            return self._refine(sp, ap, sr, a.frame_ms, voiced)
        key = (id(a), c, sr)
        with self._refine_lock:
            hit = self._refined.get(key)
            if hit is not None and hit[0] is a:
                return hit[1], hit[2]
            lock = self._refined.setdefault(("lock",) + key, threading.Lock())
        with lock:
            with self._refine_lock:
                hit = self._refined.get(key)
                if hit is not None and hit[0] is a:
                    return hit[1], hit[2]
            sp_r, ap_r = self._refine(sp, ap, sr, a.frame_ms, voiced)
            with self._refine_lock:
                self._refined[key] = (a, sp_r, ap_r)
        return sp_r, ap_r

    def _refine(self, sp, ap, sr, fms, voiced):
        p = self.p
        sp = sp.copy()
        ap = ap.copy()
        if p.smoothing > 0:
            sigma = max(0.01, p.smoothing * 10.0 / fms)
            sp = np.exp(gaussian_filter1d(np.log(np.maximum(sp, 1e-16)), sigma, axis=0, mode="nearest"))
            ap = gaussian_filter1d(ap, sigma, axis=0, mode="nearest")
        if p.artifact_reduction > 0:
            ar = float(p.artifact_reduction)
            size = 3 if fms >= 2.5 else 5
            ap = median_filter(ap, size=(size, 1), mode="nearest")
            bins = ap.shape[1]
            freqs = np.linspace(0, sr / 2, bins)
            ramp = np.clip((freqs - 3000.0) / 5000.0, 0.0, 1.0)
            floor = (ar * 0.35) * ramp
            ap[voiced] = np.maximum(ap[voiced], floor)
            lsp = np.log(np.maximum(sp, 1e-16))
            d = np.diff(lsp, axis=0)
            lim = 3.0 - 2.0 * ar
            d = np.clip(d, -lim, lim)
            lsp[1:] = lsp[0] + np.cumsum(d, axis=0)
            drift = gaussian_filter1d(lsp - np.log(np.maximum(sp, 1e-16)), 8.0, axis=0, mode="nearest")
            sp = np.exp(lsp - drift)
        return np.clip(sp, 1e-16, None), np.clip(ap, 0.0, 1.0)

    def _hybrid(self, y: np.ndarray, x: np.ndarray, sr: int, a: NaturalAnalysis) -> np.ndarray:
        p = self.p
        n = len(y)
        out = y
        voiced = (a.f0 > 0).astype(np.float64)
        if p.vuv_processing and p.unvoiced_mix > 0:
            edge_ms = 5.0 + 20.0 * p.smoothing
            uv = 1.0 - frames_to_samples(voiced, a.frame_ms, sr, n)
            uv = np.clip(smooth_curve(uv, sr, edge_ms), 0, 1) * p.unvoiced_mix
            out = out * (1 - uv[:, None]) + x[:n] * uv[:, None]
        if p.transient_preservation > 0:
            m = transient_mask(n, sr, a.onsets, p.transient_window_ms)
            v = frames_to_samples(voiced, a.frame_ms, sr, n)
            m = m * (1.0 - 0.6 * v) * p.transient_preservation
            out = out * (1 - m[:, None]) + x[:n] * m[:, None]
        return out
