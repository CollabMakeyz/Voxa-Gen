from __future__ import annotations

import copy
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

from ...models.config import GeneratorConfig
from ...models.serialization import from_dict, to_dict
from ..audio.pipeline import Cancelled
from ..samples.library import SampleLibrary
from .exporter import (
    ExportConflict, destination_folder, export_chromatic, find_conflicts, planned_files, unique_destination,
)

STATUSES = ("pending", "running", "done", "failed", "cancelled", "skipped")
CONFLICT_POLICIES = ("new_folder", "skip")


@dataclass
class BatchJob:
    name: str
    config: dict
    samples: list[list[str]] = field(default_factory=list)
    destination: str = ""
    conflict: str = "new_folder"
    id: str = field(default_factory=lambda: uuid.uuid4().hex[:8])
    status: str = "pending"
    progress: float = 0.0
    stage: str = ""
    error: str = ""
    result_folder: str = ""
    warnings: list[str] = field(default_factory=list)

    @property
    def finished(self) -> bool:
        return self.status in ("done", "failed", "cancelled", "skipped")

    def reset(self) -> None:
        self.status, self.progress, self.stage, self.error, self.result_folder = "pending", 0.0, "", "", ""
        self.warnings = []

    def summary(self) -> str:
        cfg = self.typed_config()
        m = cfg.musical
        fx = " + effects" if cfg.effects.enabled and cfg.effects.chain else ""
        return f"{cfg.mode.title()}{fx} · {m.semitones} notes · {cfg.order.mode}"

    def typed_config(self) -> GeneratorConfig:
        return from_dict(GeneratorConfig, self.config)


def make_job(name: str, config: GeneratorConfig, library: SampleLibrary, default_dir: str = "",
             conflict: str = "new_folder") -> BatchJob:
    disabled = set(config.disabled_samples)
    samples = [[s.id, s.path] for s in library.samples() if s.usable and s.id not in disabled]
    dest = destination_folder(config.export, default_dir)
    return BatchJob(name or config.export.folder_name or "Job", to_dict(copy.deepcopy(config)), samples, str(dest),
                    conflict if conflict in CONFLICT_POLICIES else "new_folder")


def job_library(job: BatchJob) -> SampleLibrary:
    lib = SampleLibrary()
    for sid, path in job.samples:
        lib.add_with_id(path, sid)
    return lib


JobEvent = Callable[[int, BatchJob], None]


def run_batch(jobs: list[BatchJob], on_event: JobEvent | None = None,
              cancel: Callable[[], bool] | None = None) -> list[BatchJob]:
    def emit(i, job):
        if on_event:
            on_event(i, job)

    for i, job in enumerate(jobs):
        if job.finished:
            continue
        if cancel and cancel():
            job.status = "cancelled"
            emit(i, job)
            continue
        job.status, job.progress, job.error, job.stage = "running", 0.0, "", "Preparing"
        emit(i, job)
        try:
            cfg = job.typed_config()
            lib = job_library(job)
            missing = [s.id for s in lib.samples() if not s.usable]
            if missing:
                raise FileNotFoundError("Missing or unreadable samples: " + ", ".join(missing))
            dest = Path(job.destination)
            if dest.exists():
                files = planned_files(cfg, [])
                if find_conflicts(dest, files) or any(dest.iterdir()):
                    if job.conflict == "skip":
                        job.status, job.stage = "skipped", "Destination already has files"
                        emit(i, job)
                        continue
                    dest = unique_destination(dest)

            def progress(stage, cur, total, label, _i=i, _job=job):
                weight = {"render": (0.0, 0.8), "write": (0.8, 0.18), "validate": (0.98, 0.02)}.get(stage, (0, 0))
                frac = (cur / total) if total else 1.0
                _job.progress = min(1.0, weight[0] + weight[1] * frac)
                _job.stage = stage
                emit(_i, _job)

            res = export_chromatic(cfg, lib, dest, overwrite=False, progress=progress, cancel=cancel)
            job.status, job.progress, job.result_folder, job.stage = "done", 1.0, str(res.folder), "Done"
            job.warnings = list(res.warnings)
        except Cancelled:
            job.status, job.stage = "cancelled", "Cancelled"
        except ExportConflict as exc:
            job.status, job.error = "failed", str(exc)
        except Exception as exc:
            job.status, job.error = "failed", str(exc) or exc.__class__.__name__
        emit(i, job)
    return jobs


def overall_progress(jobs: list[BatchJob]) -> float:
    if not jobs:
        return 0.0
    return sum(1.0 if j.finished else j.progress for j in jobs) / len(jobs)


def jobs_to_data(jobs: list[BatchJob]) -> list[dict]:
    return [to_dict(j) for j in jobs]


def jobs_from_data(data: list[dict]) -> list[BatchJob]:
    out = []
    for d in data or []:
        if isinstance(d, dict) and isinstance(d.get("config"), dict):
            j = from_dict(BatchJob, d)
            if j.status == "running":
                j.reset()
            out.append(j)
    return out
