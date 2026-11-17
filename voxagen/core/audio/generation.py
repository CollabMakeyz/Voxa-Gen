from __future__ import annotations

import os
import threading
import time
from concurrent.futures import FIRST_COMPLETED, ThreadPoolExecutor, wait
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

import numpy as np

from ...models.config import GeneratorConfig
from ..samples.library import SampleLibrary
from .dsp import peak
from .pipeline import (
    Cancelled, GainPlan, NotePlan, NoteRenderer, assemble_positions, channel_count, compute_gains,
    gap_frames, plan_notes,
)

EXPORT_MEMORY_BYTES = 1024 * 1024 * 1024

ProgressFn = Callable[[str, int, int, str], None]
CancelFn = Callable[[], bool]


def render_workers(renderer: NoteRenderer, notes: int) -> int:
    if notes <= 1:
        return 1
    env = os.environ.get("VOXAGEN_RENDER_THREADS", "").strip()
    if env.isdigit() and int(env) > 0:
        return min(int(env), notes)
    if renderer.mode == "legacy" and not renderer.original:
        return 1
    cpus = os.cpu_count() or 2
    return max(1, min(notes, cpus - 1, 12))


@dataclass
class NoteResult:
    plan: NotePlan
    frames: int
    peak: float
    warnings: list[str] = field(default_factory=list)
    info: dict = field(default_factory=dict)
    error: str = ""
    audio: np.ndarray | None = None
    path: Path | None = None
    packed: np.ndarray | None = None

    def load(self) -> np.ndarray:
        if self.audio is not None:
            return self.audio
        if self.packed is not None:
            return self.packed.astype(np.float64)
        if self.path is not None:
            return np.load(self.path).astype(np.float64)
        raise RuntimeError("note audio unavailable")


@dataclass
class Generation:
    config: GeneratorConfig
    notes: list[NoteResult]
    gains: GainPlan
    positions: list[int]
    total_frames: int
    gap_frames: int
    channels: int
    sample_rate: int
    elapsed: float

    @property
    def errors(self) -> list[NoteResult]:
        return [n for n in self.notes if n.error]

    def assemble(self) -> np.ndarray:
        out = np.zeros((self.total_frames, self.channels))
        for n, p in zip(self.notes, self.positions):
            if n.frames:
                out[p:p + n.frames] = n.load() * self.gains.gain
        return out

    def note_audio(self, i: int) -> np.ndarray:
        return self.notes[i].load() * self.gains.gain


def render_generation(config: GeneratorConfig, library: SampleLibrary, *, mode: str | None = None,
                      original: bool = False, progress: ProgressFn | None = None,
                      cancel: CancelFn | None = None, strict: bool = True,
                      work_dir: Path | None = None, only: list[int] | None = None) -> Generation:
    t0 = time.perf_counter()
    plans = plan_notes(config, library)
    renderer = NoteRenderer(config, library, mode=mode, original=original)
    ex = config.export
    ch = channel_count(ex)
    nominal = int(round(ex.fixed_duration_ms / 1000 * ex.sample_rate)) if ex.fixed_duration else 0
    total = len(plans)
    budget = [EXPORT_MEMORY_BYTES]
    budget_lock = threading.Lock()

    def keep_in_memory(nbytes: int) -> bool:
        with budget_lock:
            if nbytes <= budget[0]:
                budget[0] -= nbytes
                return True
            return False

    def one(i: int, plan: NotePlan) -> NoteResult:
        rn = renderer.render(plan)
        if rn.error:
            audio = np.zeros((nominal, ch))
            return NoteResult(plan, len(audio), 0.0, rn.warnings, rn.info, rn.error, audio=audio)
        res = NoteResult(plan, rn.frames, peak(rn.audio), rn.warnings, rn.info)
        if work_dir is not None:
            packed = rn.audio.astype(np.float32)
            if keep_in_memory(packed.nbytes):
                res.packed = packed
            else:
                p = Path(work_dir) / f"note_{i:05d}.npy"
                np.save(p, packed)
                res.path = p
        else:
            res.audio = rn.audio
        return res

    def fail(i: int, res: NoteResult):
        plan = res.plan
        return RuntimeError(f"Note {i + 1} ({plan.name}, sample '{plan.sample_id}'): {res.error}")

    todo = [i for i in range(total) if only is None or i in only]
    slots: list[NoteResult | None] = [None] * total
    for i in range(total):
        if only is not None and i not in only:
            slots[i] = NoteResult(plans[i], 0, 0.0)
    workers = render_workers(renderer, len(todo))
    if workers <= 1:
        for i in todo:
            if cancel and cancel():
                raise Cancelled()
            if progress:
                progress("render", i, total, f"{plans[i].name} · {plans[i].sample_id}")
            slots[i] = one(i, plans[i])
            if strict and slots[i].error:
                raise fail(i, slots[i])
    else:
        pool = ThreadPoolExecutor(max_workers=workers, thread_name_prefix="voxagen-render")
        try:
            futures = {pool.submit(one, i, plans[i]): i for i in todo}
            pending = set(futures)
            done_count = 0
            first_error = None
            if progress:
                progress("render", 0, total, f"{plans[todo[0]].name} · {plans[todo[0]].sample_id}" if todo else "")
            while pending:
                if cancel and cancel():
                    raise Cancelled()
                done, pending = wait(pending, timeout=0.1, return_when=FIRST_COMPLETED)
                for f in done:
                    i = futures[f]
                    slots[i] = f.result()
                    done_count += 1
                    if strict and slots[i].error and (first_error is None or i < first_error):
                        first_error = i
                    if progress:
                        progress("render", done_count, total, f"{plans[i].name} · {plans[i].sample_id}")
                if first_error is not None:
                    earlier = [futures[f] for f in pending if futures[f] < first_error]
                    if not earlier:
                        raise fail(first_error, slots[first_error])
        finally:
            pool.shutdown(wait=True, cancel_futures=True)
    results: list[NoteResult] = slots
    if progress:
        progress("render", total, total, "done")
    legacy = (mode or config.mode) == "legacy" and not original and config.musical.retune
    gains = compute_gains([n.peak for n in results], ex, legacy)
    gf = gap_frames(ex)
    positions, total_frames = assemble_positions([n.frames for n in results], gf)
    return Generation(config, results, gains, positions, total_frames, gf, ch, ex.sample_rate,
                      time.perf_counter() - t0)
