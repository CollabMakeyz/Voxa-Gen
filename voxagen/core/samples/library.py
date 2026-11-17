from __future__ import annotations

import hashlib
import os
from dataclasses import dataclass, field
from pathlib import Path

import soundfile as sf

from .naming import natural_key, sample_id_from_path

AUDIO_EXTENSIONS = {".wav"}


@dataclass
class PitchInfo:
    median_hz: float = 0.0
    note: str = ""
    cents: float = 0.0
    voiced_ratio: float = 0.0
    spread_cents: float = 0.0
    confidence: float = 0.0
    reliable: bool = False
    reason: str = ""


@dataclass
class SampleInfo:
    id: str
    path: str
    duration: float = 0.0
    sample_rate: int = 0
    subtype: str = ""
    channels: int = 0
    frames: int = 0
    content_hash: str = ""
    status: str = "ok"
    error: str = ""
    pitch: PitchInfo | None = None
    duplicate_of: str = ""

    @property
    def name(self) -> str:
        return Path(self.path).name

    @property
    def bit_depth_label(self) -> str:
        return {
            "PCM_16": "16-bit", "PCM_24": "24-bit", "PCM_32": "32-bit int",
            "PCM_U8": "8-bit", "PCM_S8": "8-bit", "FLOAT": "32-bit float", "DOUBLE": "64-bit float",
        }.get(self.subtype, self.subtype or "?")

    @property
    def usable(self) -> bool:
        return self.status == "ok"


def file_hash(path: str | Path, chunk: int = 1 << 20) -> str:
    h = hashlib.blake2b(digest_size=16)
    with open(path, "rb") as fh:
        while True:
            b = fh.read(chunk)
            if not b:
                break
            h.update(b)
    return h.hexdigest()


def probe(path: str | Path, sample_id: str | None = None) -> SampleInfo:
    path = str(path)
    info = SampleInfo(id=sample_id or sample_id_from_path(path), path=path)
    if not os.path.exists(path):
        info.status, info.error = "missing", "File not found"
        return info
    try:
        meta = sf.info(path)
        info.sample_rate = int(meta.samplerate)
        info.channels = int(meta.channels)
        info.frames = int(meta.frames)
        info.duration = meta.frames / float(meta.samplerate) if meta.samplerate else 0.0
        info.subtype = meta.subtype
        if info.frames <= 0:
            info.status, info.error = "error", "File contains no audio"
        info.content_hash = file_hash(path)
    except Exception as exc:
        info.status, info.error = "error", f"Unreadable audio: {exc}"
    return info


@dataclass
class AddResult:
    added: list[str] = field(default_factory=list)
    skipped: list[str] = field(default_factory=list)
    conflicts: list[tuple[str, str]] = field(default_factory=list)


class SampleLibrary:
    def __init__(self) -> None:
        self._samples: dict[str, SampleInfo] = {}

    def __len__(self) -> int:
        return len(self._samples)

    def __contains__(self, sample_id: str) -> bool:
        return sample_id in self._samples

    def get(self, sample_id: str) -> SampleInfo | None:
        return self._samples.get(sample_id)

    def ids(self) -> list[str]:
        return sorted(self._samples, key=natural_key)

    def samples(self) -> list[SampleInfo]:
        return [self._samples[i] for i in self.ids()]

    def usable_ids(self, exclude: set[str] | None = None) -> list[str]:
        exclude = exclude or set()
        return [i for i in self.ids() if self._samples[i].usable and i not in exclude]

    def missing(self) -> list[SampleInfo]:
        return [s for s in self.samples() if s.status == "missing"]

    def duplicates(self) -> list[SampleInfo]:
        return [s for s in self.samples() if s.duplicate_of]

    def clear(self) -> None:
        self._samples.clear()

    def add_folder(self, folder: str | Path) -> AddResult:
        folder = Path(folder)
        if not folder.is_dir():
            raise NotADirectoryError(str(folder))
        files = sorted((p for p in folder.iterdir() if p.is_file()), key=lambda p: natural_key(p.stem))
        return self.add_files(files)

    def add_files(self, paths) -> AddResult:
        result = AddResult()
        for p in paths:
            p = Path(p)
            if p.is_dir():
                sub = self.add_folder(p)
                result.added += sub.added
                result.skipped += sub.skipped
                result.conflicts += sub.conflicts
                continue
            if p.suffix.lower() not in AUDIO_EXTENSIONS:
                result.skipped.append(str(p))
                continue
            sid = sample_id_from_path(p)
            existing = self._samples.get(sid)
            if existing is not None:
                if os.path.normcase(os.path.abspath(existing.path)) != os.path.normcase(os.path.abspath(p)):
                    result.conflicts.append((str(p), sid))
                continue
            self._samples[sid] = probe(p, sid)
            result.added.append(sid)
        self._update_duplicates()
        return result

    def add_with_id(self, path: str | Path, sample_id: str) -> SampleInfo:
        self._samples[sample_id] = probe(path, sample_id)
        self._update_duplicates()
        return self._samples[sample_id]

    def add_missing(self, sample_id: str, path: str) -> SampleInfo:
        info = SampleInfo(id=sample_id, path=str(path), status="missing", error="File not found")
        self._samples[sample_id] = info
        return info

    def remove(self, sample_id: str) -> None:
        self._samples.pop(sample_id, None)
        self._update_duplicates()

    def replace(self, sample_id: str, new_path: str | Path) -> SampleInfo:
        if sample_id not in self._samples:
            raise KeyError(sample_id)
        old = self._samples[sample_id]
        info = probe(new_path, sample_id)
        info.pitch = None if info.content_hash != old.content_hash else old.pitch
        self._samples[sample_id] = info
        self._update_duplicates()
        return info

    def reload(self, sample_id: str | None = None) -> list[str]:
        changed = []
        ids = [sample_id] if sample_id else list(self._samples)
        for sid in ids:
            old = self._samples.get(sid)
            if old is None:
                continue
            info = probe(old.path, sid)
            if info.content_hash != old.content_hash or info.status != old.status:
                changed.append(sid)
            else:
                info.pitch = old.pitch
            self._samples[sid] = info
        self._update_duplicates()
        return changed

    def set_pitch(self, sample_id: str, pitch: PitchInfo) -> None:
        if sample_id in self._samples:
            self._samples[sample_id].pitch = pitch

    def _update_duplicates(self) -> None:
        seen: dict[str, str] = {}
        for s in self.samples():
            s.duplicate_of = ""
            if not s.content_hash:
                continue
            if s.content_hash in seen:
                s.duplicate_of = seen[s.content_hash]
            else:
                seen[s.content_hash] = s.id
