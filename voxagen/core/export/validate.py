from __future__ import annotations

from dataclasses import asdict, dataclass, field
from pathlib import Path

import numpy as np
import soundfile as sf

from .riff import WAVE_FORMAT_IEEE_FLOAT, WAVE_FORMAT_PCM, parse_wav

BITS = {"pcm16": 16, "pcm24": 24, "float32": 32}
SUBTYPE = {"pcm16": "PCM_16", "pcm24": "PCM_24", "float32": "FLOAT"}


@dataclass
class Check:
    name: str
    ok: bool
    detail: str = ""
    severity: str = "error"


@dataclass
class ValidationReport:
    checks: list[Check] = field(default_factory=list)

    def add(self, name, ok, detail="", severity="error"):
        self.checks.append(Check(name, bool(ok), detail, severity))

    @property
    def ok(self) -> bool:
        return all(c.ok for c in self.checks if c.severity == "error")

    @property
    def failures(self) -> list[Check]:
        return [c for c in self.checks if not c.ok and c.severity == "error"]

    @property
    def warnings(self) -> list[Check]:
        return [c for c in self.checks if not c.ok and c.severity == "warning"]

    def to_dict(self) -> dict:
        return {"ok": self.ok, "checks": [asdict(c) for c in self.checks]}


def _tolerance(bit_depth: str) -> float:
    return {"pcm16": 2.5 / 32767, "pcm24": 2.5 / 8388607, "float32": 1e-6}[bit_depth]


def _check_header(report, label, path: Path, ex, channels, frames_expected):
    try:
        info = parse_wav(path)
    except Exception as exc:
        report.add(f"{label}: RIFF structure", False, str(exc))
        return None
    report.add(f"{label}: RIFF structure", info.riff_size_ok and "data" in info.chunks and "fmt " in info.chunks,
               "RIFF size / chunk layout")
    tag = WAVE_FORMAT_IEEE_FLOAT if ex.bit_depth == "float32" else WAVE_FORMAT_PCM
    report.add(f"{label}: format", info.format_tag == tag and info.bits == BITS[ex.bit_depth],
               f"tag {info.format_tag}, {info.bits}-bit")
    report.add(f"{label}: sample rate", info.sample_rate == ex.sample_rate, f"{info.sample_rate} Hz")
    report.add(f"{label}: channels", info.channels == channels, f"{info.channels}")
    report.add(f"{label}: length", info.frames == frames_expected, f"{info.frames} / {frames_expected} frames")
    try:
        meta = sf.info(str(path))
        report.add(f"{label}: decodable", meta.frames == frames_expected and meta.subtype == SUBTYPE[ex.bit_depth],
                   f"libsndfile: {meta.subtype}, {meta.frames} frames")
    except Exception as exc:
        report.add(f"{label}: decodable", False, str(exc))
    return info


def validate_export(folder: Path, chrom_rel, note_rels, gen) -> ValidationReport:
    folder = Path(folder)
    ex = gen.config.export
    report = ValidationReport()
    tol = _tolerance(ex.bit_depth)
    full_scale = 1.0 if ex.bit_depth == "float32" else (32767 / 32768 if ex.bit_depth == "pcm16" else 8388607 / 8388608)

    if chrom_rel is not None:
        path = folder / chrom_rel
        info = _check_header(report, "chromatic", path, ex, gen.channels, gen.total_frames)
        if info is not None:
            if ex.markers:
                frames = [p for _, p in info.cues]
                report.add("chromatic: marker count", len(frames) == len(gen.notes),
                           f"{len(frames)} markers / {len(gen.notes)} notes")
                report.add("chromatic: marker positions", frames == list(gen.positions),
                           "positions match note starts" if frames == list(gen.positions) else "mismatch")
                labels = [info.labels.get(i) for i, _ in info.cues]
                report.add("chromatic: marker labels", labels == [n.plan.name for n in gen.notes], "")
            else:
                report.add("chromatic: no markers requested", not info.cues, "")
            try:
                data, _ = sf.read(str(path), dtype="float64", always_2d=True)
                worst = 0.0
                for i, (n, p) in enumerate(zip(gen.notes, gen.positions)):
                    if n.frames:
                        expected = np.clip(gen.note_audio(i), -1, 1)
                        worst = max(worst, float(np.max(np.abs(data[p:p + n.frames] - expected))))
                report.add("chromatic: content matches render", worst <= tol, f"max deviation {worst:.2e}")
                over = (np.abs(data) > full_scale) if ex.bit_depth == "float32" else (np.abs(data) >= full_scale)
                clipped = int(np.sum(over))
                report.add("chromatic: no unintended clipping", clipped == 0 or not ex.prevent_clipping,
                           f"{clipped} samples at full scale")
                if clipped and not ex.prevent_clipping:
                    report.add("chromatic: clipping (protection disabled)", False,
                               f"{clipped} samples at full scale", "warning")
                silent = [n.plan.name for n in gen.notes if n.peak * gen.gains.gain < 1e-4]
                report.add("chromatic: audible notes", not silent, ", ".join(silent[:8]), "warning")
            except Exception as exc:
                report.add("chromatic: content", False, str(exc))

    if note_rels:
        report.add("notes: file count", len(note_rels) == len(gen.notes) and all((folder / r).exists() for r in note_rels),
                   f"{sum((folder / r).exists() for r in note_rels)} / {len(gen.notes)}")
        bad = []
        worst = 0.0
        for i, rel in enumerate(note_rels):
            path = folder / rel
            sub = _NullReport()
            info = _check_header(sub, rel.name if hasattr(rel, "name") else str(rel), path, ex, gen.channels,
                                 gen.notes[i].frames)
            if info is None or not sub.ok:
                bad.append(f"{rel}: " + "; ".join(c.detail for c in sub.failures))
                continue
            data, _ = sf.read(str(path), dtype="float64", always_2d=True)
            if len(data):
                worst = max(worst, float(np.max(np.abs(data - np.clip(gen.note_audio(i), -1, 1)))))
        report.add("notes: headers and lengths", not bad, "; ".join(bad[:5]) or "all files valid")
        report.add("notes: content matches render", worst <= tol, f"max deviation {worst:.2e}")
    return report


class _NullReport(ValidationReport):
    pass
