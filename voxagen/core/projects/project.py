from __future__ import annotations

import datetime as _dt
import json
import os
from dataclasses import dataclass, field
from pathlib import Path

from ... import __version__
from ...models.app_settings import atomic_write_json
from ...models.config import GeneratorConfig
from ...models.serialization import from_dict, to_dict
from ..samples.library import SampleLibrary, file_hash

FORMAT = "voxagen-project"
VERSION = 1
PROJECT_EXT = ".vxproj"


class ProjectError(Exception):
    pass


@dataclass
class ProjectSample:
    id: str
    path: str
    rel_path: str = ""
    content_hash: str = ""
    enabled: bool = True
    resolved: str = ""
    changed: bool = False


@dataclass
class LoadedProject:
    path: Path
    name: str
    config: GeneratorConfig
    samples: list[ProjectSample]
    presets: dict = field(default_factory=dict)
    batch: list[dict] = field(default_factory=list)
    app_version: str = ""
    newer_format: bool = False

    @property
    def missing(self) -> list[ProjectSample]:
        return [s for s in self.samples if not s.resolved]

    @property
    def changed(self) -> list[ProjectSample]:
        return [s for s in self.samples if s.resolved and s.changed]

    def apply_to(self, library: SampleLibrary) -> None:
        library.clear()
        for s in self.samples:
            if s.resolved:
                library.add_with_id(s.resolved, s.id)
            else:
                library.add_missing(s.id, s.path)


def _now() -> str:
    return _dt.datetime.now().isoformat(timespec="seconds")


def save_project(path: str | Path, config: GeneratorConfig, library: SampleLibrary, *,
                 batch: list[dict] | None = None, name: str = "", created: str = "") -> Path:
    path = Path(path)
    if path.suffix.lower() != PROJECT_EXT:
        path = path.with_suffix(PROJECT_EXT)
    disabled = set(config.disabled_samples)
    samples = []
    for s in library.samples():
        try:
            rel = os.path.relpath(s.path, path.parent)
        except ValueError:
            rel = ""
        samples.append({"id": s.id, "path": str(Path(s.path).resolve()) if s.path else "",
                        "rel_path": rel.replace("\\", "/"), "content_hash": s.content_hash,
                        "enabled": s.id not in disabled})
    data = {
        "format": FORMAT, "version": VERSION, "app_version": __version__,
        "created": created or _now(), "modified": _now(), "name": name or path.stem,
        "config": to_dict(config),
        "samples": samples,
        "presets": {"sequence": config.order.sequence_name, "lab_profile": config.lab_profile_name,
                    "effects": config.effects.preset_name},
        "batch": list(batch or []),
    }
    atomic_write_json(path, data)
    return path


def load_project(path: str | Path) -> LoadedProject:
    path = Path(path)
    try:
        raw = json.loads(path.read_text("utf-8"))
    except FileNotFoundError as exc:
        raise ProjectError(f"Project file not found: {path}") from exc
    except (OSError, ValueError) as exc:
        raise ProjectError(f"Could not read the project file: {exc}") from exc
    if not isinstance(raw, dict) or raw.get("format") != FORMAT:
        raise ProjectError("This is not a Voxa GEN project file.")
    version = int(raw.get("version", 1) or 1)
    config = from_dict(GeneratorConfig, raw.get("config") or {})
    samples = []
    for d in raw.get("samples") or []:
        if not isinstance(d, dict) or not d.get("id"):
            continue
        s = ProjectSample(str(d["id"]), str(d.get("path", "")), str(d.get("rel_path", "")),
                          str(d.get("content_hash", "")), bool(d.get("enabled", True)))
        _resolve(s, path.parent)
        samples.append(s)
    config.sample_folder = ""
    config.sample_paths = [s.resolved or s.path for s in samples]
    config.disabled_samples = [s.id for s in samples if not s.enabled]
    return LoadedProject(path, str(raw.get("name") or path.stem), config, samples,
                         dict(raw.get("presets") or {}), list(raw.get("batch") or []),
                         str(raw.get("app_version", "")), version > VERSION)


def _resolve(s: ProjectSample, base: Path) -> None:
    candidates = [s.path]
    if s.rel_path:
        candidates.append(str((base / s.rel_path).resolve()))
    for c in candidates:
        if c and os.path.isfile(c):
            s.resolved = c
            if s.content_hash:
                try:
                    s.changed = file_hash(c) != s.content_hash
                except OSError:
                    s.changed = False
            return


def find_in_folder(missing: list[ProjectSample], folder: str | Path) -> dict[str, str]:
    folder = Path(folder)
    by_name: dict[str, list[Path]] = {}
    for root, _, files in os.walk(folder):
        for f in files:
            if f.lower().endswith(".wav"):
                by_name.setdefault(f.lower(), []).append(Path(root) / f)
    found: dict[str, str] = {}
    for s in missing:
        name = Path(s.path).name.lower()
        cands = by_name.get(name, [])
        best = None
        for c in cands:
            try:
                if s.content_hash and file_hash(c) == s.content_hash:
                    best = c
                    break
            except OSError:
                continue
        if best is None and cands:
            best = cands[0]
        if best is not None:
            found[s.id] = str(best)
    return found
