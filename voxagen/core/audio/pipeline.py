from __future__ import annotations

import hashlib
import os
import threading
from collections import OrderedDict
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np

from ...models.config import ExportSettings, GeneratorConfig
from ...models.serialization import to_dict
from ...paths import cache_dir
from ..pitch.tuning import frequency_of, midi_of, note_name
from ..samples.library import SampleLibrary
from ..sequences.order import build_order
from .dsp import (
    apply_fades, conform_channels, db_to_gain, fit_length, load_audio, peak, resample, trim_silence,
)
from .engines.base import AnalysisCache, get_engine

LEGACY_PEAK = 0.98


class Cancelled(Exception):
    pass


@dataclass
class NotePlan:
    index: int
    midi: int
    name: str
    target_hz: float
    sample_id: str


@dataclass
class RenderedNote:
    plan: NotePlan
    audio: np.ndarray
    warnings: list[str] = field(default_factory=list)
    info: dict = field(default_factory=dict)
    error: str = ""

    @property
    def frames(self) -> int:
        return len(self.audio)


def channel_count(export: ExportSettings) -> int:
    return 2 if export.channels == "stereo" else 1


def plan_notes(config: GeneratorConfig, library: SampleLibrary) -> list[NotePlan]:
    m = config.musical
    usable = library.usable_ids(set(config.disabled_samples))
    order = build_order(m.semitones, usable, config.order)
    start = midi_of(m.start_note, m.start_octave)
    plans = []
    for i, sid in enumerate(order):
        midi = start + i
        hz = frequency_of(midi, m.a4_hz, m.temperament, m.temperament_root, m.custom_cents)
        plans.append(NotePlan(i, midi, note_name(midi), hz, sid))
    return plans


class SourcePool:

    def __init__(self, max_bytes: int = 256 * 1024 * 1024):
        self.max_bytes = max_bytes
        self._items: OrderedDict[str, tuple[np.ndarray, int]] = OrderedDict()
        self._size = 0
        self._lock = threading.Lock()

    def get(self, path: str, content_hash: str) -> tuple[np.ndarray, int]:
        with self._lock:
            if content_hash in self._items:
                self._items.move_to_end(content_hash)
                return self._items[content_hash]
        x, sr = load_audio(path)
        with self._lock:
            self._items[content_hash] = (x, sr)
            self._size += x.nbytes
            while self._size > self.max_bytes and len(self._items) > 1:
                _, (old, _) = self._items.popitem(last=False)
                self._size -= old.nbytes
        return x, sr


_ANALYSIS = AnalysisCache()
_SOURCES = SourcePool()


def clear_memory_caches() -> None:
    _ANALYSIS.clear()
    with _SOURCES._lock:
        _SOURCES._items.clear()
        _SOURCES._size = 0


class NoteRenderer:

    def __init__(self, config: GeneratorConfig, library: SampleLibrary, mode: str | None = None,
                 use_disk_cache: bool = True, original: bool = False, effects: bool | None = None):
        self.config = config
        self.library = library
        self.mode = mode or config.mode
        self.original = original or not config.musical.retune
        self.engine = None if self.original else get_engine(self.mode, config)
        self.use_disk_cache = use_disk_cache
        from ..effects.chain import chain_key
        self.fx_key = chain_key(config.effects) if (effects if effects is not None else not original) else ""
        self.cache_root = cache_dir() / "renders"
        self.cache_root.mkdir(parents=True, exist_ok=True)

    def _key(self, plan: NotePlan, sample_hash: str, ratio: float) -> str:
        ex = self.config.export
        parts = [
            "v1", sample_hash, "original" if self.original else self.engine.render_key(),
            f"{plan.target_hz:.6f}", str(ex.sample_rate), ex.channels, f"{ratio:.6f}",
            f"trim={ex.trim_silence}:{ex.trim_threshold_db}",
        ]
        if self.fx_key:
            parts.append(self.fx_key)
        return hashlib.blake2b("|".join(parts).encode(), digest_size=20).hexdigest()

    def duration_ratio(self, source_seconds: float) -> float:
        ex = self.config.export
        if ex.fixed_duration and ex.fit_mode == "stretch" and source_seconds > 0:
            return max(0.1, (ex.fixed_duration_ms / 1000.0) / source_seconds)
        return 1.0

    def render_raw(self, plan: NotePlan) -> RenderedNote:
        info = self.library.get(plan.sample_id)
        if info is None or not info.usable:
            raise FileNotFoundError(f"Sample '{plan.sample_id}' is not available")
        x, sr = _SOURCES.get(info.path, info.content_hash)
        ex = self.config.export
        if ex.trim_silence:
            x = trim_silence(x, sr, ex.trim_threshold_db)
            if len(x) == 0:
                raise ValueError(f"Sample '{plan.sample_id}' is silent below {ex.trim_threshold_db} dBFS")
        ratio = self.duration_ratio(len(x) / sr)
        key = self._key(plan, info.content_hash, ratio)
        path = self.cache_root / f"{key}.npy"
        if self.use_disk_cache and path.exists():
            try:
                audio = np.load(path)
                meta = _read_meta(path)
                return RenderedNote(plan, audio, meta.get("warnings", []), meta.get("info", {}))
            except Exception:
                pass
        warnings: list[str] = []
        info_d: dict = {}
        if self.original:
            y, y_sr = x, sr
            if ratio != 1.0:
                warnings.append("Stretch is not applied to original (unprocessed) audio.")
        else:
            akey = (info.content_hash, self.engine.analysis_key(), ex.trim_silence, ex.trim_threshold_db)
            analysis = _ANALYSIS.get_or_create(akey, lambda: self.engine.analyze(x, sr))
            res = self.engine.render(analysis, x, sr, plan.target_hz, ratio)
            y, y_sr, warnings, info_d = res.audio, res.sr, res.warnings, res.info
            if not self.engine.keeps_channels and x.shape[1] > 1 and channel_count(ex) > 1:
                warnings.append("Legacy chain is mono; output duplicated to stereo.")
        q = self.engine.resampling_quality if self.engine else "vhq"
        y = resample(y, y_sr, ex.sample_rate, q)
        y = conform_channels(y, channel_count(ex))
        if self.fx_key:
            from ..effects.chain import apply_chain
            y = apply_chain(y, ex.sample_rate, self.config.effects, plan.target_hz, plan.index)
        if self.use_disk_cache:
            try:
                tmp = path.with_suffix(f".{os.getpid()}.{threading.get_ident()}.tmp.npy")
                np.save(tmp, y.astype(np.float32))
                os.replace(tmp, path)
                _write_meta(path, {"warnings": warnings, "info": _jsonable(info_d)})
            except OSError:
                pass
        return RenderedNote(plan, y.astype(np.float64), warnings, info_d)

    def render(self, plan: NotePlan) -> RenderedNote:
        try:
            raw = self.render_raw(plan)
        except Exception as exc:
            return RenderedNote(plan, np.zeros((0, channel_count(self.config.export))), [], {}, str(exc))
        raw.audio = post_process_note(raw.audio.astype(np.float64), self.config.export, self.mode == "legacy"
                                      and not self.original)
        return raw


def _jsonable(d: dict) -> dict:
    out = {}
    for k, v in d.items():
        if isinstance(v, (np.floating, np.integer)):
            v = v.item()
        if isinstance(v, (int, float, str, bool)) or v is None:
            out[k] = v
    return out


def _meta_path(npy: Path) -> Path:
    return npy.with_suffix(".json")


def _read_meta(npy: Path) -> dict:
    import json
    try:
        return json.loads(_meta_path(npy).read_text("utf-8"))
    except Exception:
        return {}


def _write_meta(npy: Path, meta: dict) -> None:
    import json
    _meta_path(npy).write_text(json.dumps(meta), "utf-8")


def post_process_note(x: np.ndarray, ex: ExportSettings, legacy: bool = False) -> np.ndarray:
    sr = ex.sample_rate
    target = int(round(ex.fixed_duration_ms / 1000.0 * sr)) if ex.fixed_duration else 0
    if legacy:
        x = apply_fades(x, sr, ex.fade_in_ms, ex.fade_out_ms)
        if target:
            x, _ = fit_length(x, target, "pad_trim" if ex.fit_mode == "stretch" else ex.fit_mode, sr, 0.0)
        if ex.normalize:
            pk = peak(x)
            if pk > 1e-9:
                x = x * (LEGACY_PEAK / pk)
        return x
    audible = x
    pad = 0
    if target:
        if len(x) > target or ex.fit_mode == "stretch":
            audible, _ = fit_length(x, target, ex.fit_mode, sr)
        if len(audible) < target:
            pad = target - len(audible)
    audible = apply_fades(audible, sr, ex.fade_in_ms, ex.fade_out_ms)
    if ex.normalize and ex.normalize_mode == "per_note":
        pk = peak(audible)
        if pk > 1e-9:
            audible = audible * (db_to_gain(ex.normalize_peak_db) / pk)
    if pad:
        audible = np.concatenate([audible, np.zeros((pad, audible.shape[1]))], axis=0)
    return audible


@dataclass
class GainPlan:
    gain: float
    clip_protected: bool
    peak_before: float
    peak_after: float
    reduction_db: float = 0.0


def compute_gains(peaks: list[float], ex: ExportSettings, legacy: bool = False) -> GainPlan:
    pk = max(peaks) if peaks else 0.0
    g = 1.0
    if ex.normalize and ex.normalize_mode == "global" and not legacy and pk > 1e-9:
        g = db_to_gain(ex.normalize_peak_db) / pk
    g *= db_to_gain(ex.master_volume_db)
    after = pk * g
    ceiling = 1.0 if ex.bit_depth == "float32" else 0.999
    if ex.prevent_clipping and after > ceiling:
        reduction = after / ceiling
        return GainPlan(g / reduction, True, pk, ceiling, 20.0 * float(np.log10(reduction)))
    return GainPlan(g, False, pk, after)


def assemble_positions(lengths: list[int], gap_frames: int) -> tuple[list[int], int]:
    pos, cur = [], 0
    for i, n in enumerate(lengths):
        pos.append(cur)
        cur += n
        if i < len(lengths) - 1:
            cur += gap_frames
    return pos, cur


def gap_frames(ex: ExportSettings) -> int:
    return max(0, int(round(ex.gap_ms / 1000.0 * ex.sample_rate)))


def config_fingerprint(config: GeneratorConfig, library: SampleLibrary) -> str:
    import json
    d = to_dict(config)
    d.pop("lab_profile_name", None)
    d["_samples"] = [(s.id, s.content_hash, s.status) for s in library.samples()]
    return hashlib.blake2b(json.dumps(d, sort_keys=True).encode(), digest_size=16).hexdigest()
