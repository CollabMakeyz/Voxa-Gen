from __future__ import annotations

import datetime as _dt
import json
import os
import re
import shutil
import string
import uuid
from dataclasses import dataclass, field
from pathlib import Path

from ... import __version__
from ...models.config import ExportSettings, GeneratorConfig
from ...models.serialization import to_dict
from ..audio.generation import CancelFn, Generation, ProgressFn, render_generation
from ..audio.pipeline import Cancelled
from ..samples.library import SampleLibrary
from .riff import WavWriter
from .validate import ValidationReport, validate_export

_INVALID_CHARS = re.compile(r'[<>:"/\\|?*\x00-\x1f]')


class ExportError(Exception):
    pass


class ExportConflict(ExportError):
    def __init__(self, conflicts: list[Path], destination: Path):
        self.conflicts = conflicts
        self.destination = destination
        super().__init__(f"{len(conflicts)} file(s) already exist in {destination}")


@dataclass
class ExportResult:
    folder: Path
    chromatic: Path | None
    notes: list[Path]
    info_file: Path
    validation: ValidationReport
    generation: Generation
    warnings: list[str] = field(default_factory=list)


def sanitize_filename(name: str) -> str:
    name = _INVALID_CHARS.sub("_", name).strip().rstrip(".")
    return name or "untitled"


TEMPLATE_FIELDS = {"index", "note", "pitch", "octave", "midi", "sample", "hz"}


def validate_template(template: str) -> str | None:
    try:
        fields = {f for _, f, _, _ in string.Formatter().parse(template) if f}
    except ValueError as exc:
        return f"Invalid template: {exc}"
    unknown = {f.split(":")[0] for f in fields} - TEMPLATE_FIELDS
    if unknown:
        return f"Unknown field(s): {', '.join(sorted(unknown))}. Use: {', '.join(sorted(TEMPLATE_FIELDS))}"
    try:
        format_note_name(template, 0, "C#4", 61, "a2", 277.18)
    except Exception as exc:
        return f"Invalid template: {exc}"
    return None


def format_note_name(template: str, index0: int, note: str, midi: int, sample: str, hz: float) -> str:
    pitch = note.rstrip("-0123456789")
    octave = note[len(pitch):]
    return sanitize_filename(template.format(index=index0 + 1, note=note, pitch=pitch, octave=octave,
                                             midi=midi, sample=sample, hz=round(hz, 2)))


def destination_folder(ex: ExportSettings, default_dir: str = "") -> Path:
    base = ex.output_dir or default_dir or str(Path.home() / "Documents")
    return Path(base) / sanitize_filename(ex.folder_name or "Voxa GEN Export")


def planned_files(config: GeneratorConfig, note_names: list[tuple[int, str, int, str, float]]) -> list[Path]:
    ex = config.export
    files = [Path("export_info.json")]
    if ex.write_chromatic:
        files.append(Path(sanitize_filename(ex.chromatic_name) + ".wav"))
    if ex.write_individual:
        sub = sanitize_filename(ex.samples_subfolder or "samples")
        for idx, note, midi, sample, hz in note_names:
            files.append(Path(sub) / (format_note_name(ex.note_name_template, idx, note, midi, sample, hz) + ".wav"))
    return files


def find_conflicts(dest: Path, files: list[Path]) -> list[Path]:
    return [dest / f for f in files if (dest / f).exists()]


def unique_destination(dest: Path) -> Path:
    if not dest.exists():
        return dest
    i = 2
    while True:
        cand = dest.with_name(f"{dest.name} ({i})")
        if not cand.exists():
            return cand
        i += 1


def export_chromatic(config: GeneratorConfig, library: SampleLibrary, dest: Path, *,
                     overwrite: bool = False, progress: ProgressFn | None = None,
                     cancel: CancelFn | None = None) -> ExportResult:
    ex = config.export
    if not (ex.write_chromatic or ex.write_individual):
        raise ExportError("Nothing to export: enable the full chromatic and/or individual notes.")
    err = validate_template(ex.note_name_template)
    if err:
        raise ExportError(err)
    dest = Path(dest)
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.parent / f".voxagen-tmp-{uuid.uuid4().hex[:10]}"
    work = tmp / "_work"
    work.mkdir(parents=True)
    try:
        gen = render_generation(config, library, progress=progress, cancel=cancel, strict=True, work_dir=work)
        names = [(n.plan.index, n.plan.name, n.plan.midi, n.plan.sample_id, n.plan.target_hz) for n in gen.notes]
        files = planned_files(config, names)
        rel_names = [str(f).lower() for f in files]
        if len(set(rel_names)) != len(rel_names):
            raise ExportError("The note file name template produces duplicate file names; include {index}.")
        conflicts = find_conflicts(dest, files)
        if conflicts and not overwrite:
            raise ExportConflict(conflicts, dest)

        chrom_rel = files[1] if ex.write_chromatic else None
        note_rels = files[2:] if ex.write_chromatic else files[1:]
        total_steps = len(gen.notes) * (int(ex.write_chromatic) + int(ex.write_individual))
        step = 0

        def tick(label):
            nonlocal step
            if cancel and cancel():
                raise Cancelled()
            if progress:
                progress("write", step, total_steps, label)
            step += 1

        ch = gen.channels
        if chrom_rel is not None:
            with WavWriter(tmp / chrom_rel, ex.sample_rate, ch, ex.bit_depth, ex.dither) as w:
                for i, (note, pos) in enumerate(zip(gen.notes, gen.positions)):
                    tick(f"chromatic · {note.plan.name}")
                    if w.frames != pos:
                        w.write_silence(pos - w.frames)
                    if ex.markers:
                        w.add_marker(pos, note.plan.name)
                    w.write(gen.note_audio(i))
                if w.frames != gen.total_frames:
                    w.write_silence(gen.total_frames - w.frames)
        if ex.write_individual:
            if note_rels:
                (tmp / note_rels[0]).parent.mkdir(parents=True, exist_ok=True)
            for i, (note, rel) in enumerate(zip(gen.notes, note_rels)):
                tick(f"note {i + 1} · {note.plan.name}")
                with WavWriter(tmp / rel, ex.sample_rate, ch, ex.bit_depth, ex.dither) as w:
                    w.write(gen.note_audio(i))

        if progress:
            progress("validate", 0, 1, "validating files")
        report = validate_export(tmp, chrom_rel, note_rels, gen)
        info = build_info(config, gen, chrom_rel, note_rels, report)
        (tmp / "export_info.json").write_text(json.dumps(info, indent=2, ensure_ascii=False), "utf-8")
        shutil.rmtree(work, ignore_errors=True)
        if not report.ok:
            raise ExportError("Validation failed:\n" + "\n".join(f"• {c.name}: {c.detail}" for c in report.failures))
        if cancel and cancel():
            raise Cancelled()
        _finalize(tmp, dest)
        warnings = sorted({w for n in gen.notes for w in n.warnings})
        if gen.gains.clip_protected:
            warnings.append(f"Clip protection lowered the output by {gen.gains.reduction_db:.2f} dB.")
        return ExportResult(dest, dest / chrom_rel if chrom_rel else None, [dest / r for r in note_rels],
                            dest / "export_info.json", report, gen, warnings)
    except BaseException:
        shutil.rmtree(tmp, ignore_errors=True)
        raise


def _finalize(tmp: Path, dest: Path) -> None:
    if not dest.exists():
        os.replace(tmp, dest)
        return
    for root, _, files in os.walk(tmp):
        rel = Path(root).relative_to(tmp)
        (dest / rel).mkdir(parents=True, exist_ok=True)
        for f in files:
            os.replace(Path(root) / f, dest / rel / f)
    shutil.rmtree(tmp, ignore_errors=True)


def build_info(config: GeneratorConfig, gen: Generation, chrom_rel, note_rels, report: ValidationReport) -> dict:
    notes = []
    for i, n in enumerate(gen.notes):
        notes.append({
            "index": i + 1, "note": n.plan.name, "midi": n.plan.midi, "target_hz": round(n.plan.target_hz, 4),
            "sample": n.plan.sample_id, "start_frame": gen.positions[i], "frames": n.frames,
            "file": str(note_rels[i]).replace("\\", "/") if i < len(note_rels) else None,
            "source_hz": round(float(n.info.get("source_hz", 0) or 0), 3), "warnings": n.warnings,
        })
    return {
        "app": "Voxa GEN", "version": __version__, "format": 1,
        "created": _dt.datetime.now().isoformat(timespec="seconds"),
        "mode": config.mode,
        "chromatic": str(chrom_rel).replace("\\", "/") if chrom_rel else None,
        "sample_rate": gen.sample_rate, "channels": gen.channels, "bit_depth": config.export.bit_depth,
        "total_frames": gen.total_frames, "gap_frames": gen.gap_frames,
        "gain": {"linear": gen.gains.gain, "clip_protected": gen.gains.clip_protected,
                 "peak_after": gen.gains.peak_after},
        "render_seconds": round(gen.elapsed, 3),
        "notes": notes,
        "validation": report.to_dict(),
        "settings": to_dict(config),
    }
