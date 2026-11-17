from __future__ import annotations

import copy
import datetime as _dt
import json
import re
from dataclasses import dataclass, field
from pathlib import Path

from ...models.app_settings import atomic_write_json
from ...models.config import (
    ExportSettings, GeneratorConfig, LegacyParams, NaturalParams, RobotParams,
)
from ...models.serialization import from_dict, to_dict
from ...paths import presets_dir
from ..sequences.order import BF_CLASSIC_NAME, BF_CLASSIC_TOKENS

FORMAT = "voxagen-preset"
VERSION = 1
KINDS = {
    "sequence": "Sequences",
    "natural": "Natural mode",
    "robot": "Robot mode",
    "legacy": "Legacy mode",
    "lab": "Lab profiles",
    "export": "Export settings",
    "processing": "Full configurations",
    "effects": "Effect chains",
}
_KIND_TYPES = {"natural": NaturalParams, "lab": NaturalParams, "robot": RobotParams,
               "legacy": LegacyParams, "export": ExportSettings, "processing": GeneratorConfig}


class PresetError(Exception):
    pass


@dataclass
class Preset:
    kind: str
    name: str
    data: dict = field(default_factory=dict)
    description: str = ""
    builtin: bool = False
    modified: bool = False
    created: str = ""

    def to_file(self) -> dict:
        return {"format": FORMAT, "version": VERSION, "kind": self.kind, "name": self.name,
                "description": self.description, "created": self.created or _now(), "data": self.data}

    def tokens(self) -> list[str]:
        return [str(t) for t in self.data.get("tokens", [])]

    @property
    def category(self) -> str:
        return str(self.data.get("category", "")) if self.kind == "effects" else ""

    def typed(self):
        tp = _KIND_TYPES.get(self.kind)
        return from_dict(tp, self.data) if tp else None


def _now() -> str:
    return _dt.datetime.now().isoformat(timespec="seconds")


def _slug(name: str) -> str:
    s = re.sub(r"[^\w\-. ]+", "_", name.strip(), flags=re.UNICODE).strip(" .")
    return s or "preset"


def _builtins() -> list[Preset]:
    nat_clean = NaturalParams()
    nat_expr = NaturalParams(humanization=0.6, pitch_accuracy=0.85, transient_preservation=0.6, smoothing=0.25)
    nat_smooth = NaturalParams(smoothing=0.7, artifact_reduction=0.8, transient_preservation=0.3)
    nat_ultra = NaturalParams(quality="ultra", artifact_reduction=0.6)
    fl16 = ExportSettings()
    studio = ExportSettings(bit_depth="pcm24", channels="stereo", normalize=True, normalize_peak_db=-1.0,
                            fade_in_ms=2.0, fade_out_ms=15.0)
    return [
        Preset("sequence", BF_CLASSIC_NAME, {"tokens": list(BF_CLASSIC_TOKENS)},
               "Classic BF vocal order (45 elements, exact).", True),
        Preset("sequence", "Vowels A E I O U", {"tokens": ["a", "e", "i", "o", "u"]}, "Plain vowel cycle.", True),
        Preset("natural", "Natural · Clean", to_dict(nat_clean), "Exact pitch, full formant preservation.", True),
        Preset("natural", "Natural · Expressive", to_dict(nat_expr),
               "Keeps natural micro-variation (zero-mean, capped) and more attack detail.", True),
        Preset("natural", "Natural · Smooth", to_dict(nat_smooth), "Stronger smoothing and artifact reduction.", True),
        Preset("natural", "Natural · Ultra", to_dict(nat_ultra), "1 ms analysis frames. Slowest, most detailed.", True),
        Preset("robot", "Robot · Default", to_dict(RobotParams()), "Fast profile.", True),
        Preset("robot", "Robot · Fastest", to_dict(RobotParams(frame_period_ms=15.0, resampling_quality="lq")),
               "Lowest cost.", True),
        Preset("legacy", "Legacy · Classic", to_dict(LegacyParams()), "Classic chain.", True),
        Preset("lab", "Lab · Default", to_dict(NaturalParams()), "Starting point for experiments.", True),
        Preset("export", "FL Studio · 16-bit 48 kHz", to_dict(fl16), "Slicex markers, mono 16-bit.", True),
        Preset("export", "Studio · 24-bit stereo", to_dict(studio), "24-bit stereo, normalized to -1 dBFS.", True),
    ] + _effect_builtins()


def _effect_builtins() -> list[Preset]:
    from ..effects.presets import BUILTIN_EFFECT_PRESETS, normalize_data
    return [Preset("effects", name, normalize_data({"category": cat, "chain": slots}), desc, True)
            for cat, name, desc, slots in BUILTIN_EFFECT_PRESETS]


class PresetManager:
    def __init__(self, root: Path | None = None):
        self.root = Path(root) if root else presets_dir()
        self.root.mkdir(parents=True, exist_ok=True)
        self._native = {(p.kind, p.name): p for p in _builtins()}

    def _dir(self, kind: str) -> Path:
        if kind not in KINDS:
            raise PresetError(f"Unknown preset kind: {kind}")
        d = self.root / kind
        d.mkdir(parents=True, exist_ok=True)
        return d

    def _path(self, kind: str, name: str) -> Path:
        return self._dir(kind) / f"{_slug(name)}.vxpreset.json"

    def _read(self, path: Path) -> Preset:
        raw = json.loads(path.read_text("utf-8"))
        return parse_preset(raw)

    def list(self, kind: str) -> list[Preset]:
        out: dict[str, Preset] = {}
        for (k, n), p in self._native.items():
            if k == kind:
                out[n] = copy.deepcopy(p)
        for f in sorted(self._dir(kind).glob("*.vxpreset.json")):
            try:
                p = self._read(f)
            except Exception:
                continue
            if p.kind != kind:
                continue
            if (kind, p.name) in self._native:
                p.builtin, p.modified = True, True
            out[p.name] = p
        builtins = [p for p in out.values() if p.builtin]
        users = sorted((p for p in out.values() if not p.builtin), key=lambda p: p.name.lower())
        return builtins + users

    def get(self, kind: str, name: str) -> Preset | None:
        for p in self.list(kind):
            if p.name == name:
                return p
        return None

    def exists(self, kind: str, name: str) -> bool:
        return self.get(kind, name) is not None

    def save(self, preset: Preset) -> Preset:
        if not preset.name.strip():
            raise PresetError("Preset name cannot be empty.")
        if preset.kind == "sequence" and not preset.tokens():
            raise PresetError("A sequence preset needs at least one element.")
        if preset.kind == "effects":
            from ..effects.presets import normalize_data
            preset.data = normalize_data(preset.data)
            if not preset.data["chain"]:
                raise PresetError("An effect preset needs at least one effect.")
        preset.created = preset.created or _now()
        atomic_write_json(self._path(preset.kind, preset.name), preset.to_file())
        return self.get(preset.kind, preset.name)

    def rename(self, kind: str, old: str, new: str) -> Preset:
        p = self.get(kind, old)
        if p is None:
            raise PresetError(f"Preset '{old}' not found.")
        if p.builtin:
            raise PresetError("Native presets cannot be renamed; duplicate it instead.")
        if self.exists(kind, new):
            raise PresetError(f"A preset named '{new}' already exists.")
        p.name = new
        self.save(p)
        self._path(kind, old).unlink(missing_ok=True)
        return self.get(kind, new)

    def duplicate(self, kind: str, name: str, new_name: str | None = None) -> Preset:
        p = self.get(kind, name)
        if p is None:
            raise PresetError(f"Preset '{name}' not found.")
        new_name = new_name or self.free_name(kind, f"{name} copy")
        if self.exists(kind, new_name):
            raise PresetError(f"A preset named '{new_name}' already exists.")
        q = Preset(kind, new_name, copy.deepcopy(p.data), p.description)
        return self.save(q)

    def delete(self, kind: str, name: str) -> None:
        p = self.get(kind, name)
        if p is None:
            return
        if p.builtin:
            raise PresetError("Native presets cannot be deleted; use Restore to undo changes.")
        self._path(kind, name).unlink(missing_ok=True)

    def restore(self, kind: str, name: str) -> None:
        if (kind, name) in self._native:
            self._path(kind, name).unlink(missing_ok=True)

    def restore_all(self) -> int:
        n = 0
        for (k, name) in self._native:
            path = self._path(k, name)
            if path.exists():
                path.unlink()
                n += 1
        return n

    def free_name(self, kind: str, base: str) -> str:
        if not self.exists(kind, base):
            return base
        i = 2
        while self.exists(kind, f"{base} {i}"):
            i += 1
        return f"{base} {i}"

    def export_to(self, kind: str, name: str, path: str | Path) -> None:
        p = self.get(kind, name)
        if p is None:
            raise PresetError(f"Preset '{name}' not found.")
        atomic_write_json(Path(path), p.to_file())

    def import_from(self, path: str | Path) -> Preset:
        try:
            raw = json.loads(Path(path).read_text("utf-8"))
        except Exception as exc:
            raise PresetError(f"Could not read preset file: {exc}") from exc
        p = parse_preset(raw)
        p.builtin = p.modified = False
        p.name = self.free_name(p.kind, p.name)
        return self.save(p)


def parse_preset(raw: dict) -> Preset:
    if not isinstance(raw, dict):
        raise PresetError("Not a preset file.")
    if raw.get("format") != FORMAT:
        if "tokens" in raw:
            return Preset("sequence", str(raw.get("name", "Imported sequence")), {"tokens": list(raw["tokens"])})
        raise PresetError("Not a Voxa GEN preset (missing format marker).")
    version = int(raw.get("version", 1))
    if version > VERSION:
        pass
    kind = raw.get("kind")
    if kind not in KINDS:
        raise PresetError(f"Unknown preset kind: {kind}")
    data = raw.get("data") or {}
    tp = _KIND_TYPES.get(kind)
    if tp is not None:
        data = to_dict(from_dict(tp, data))
    elif kind == "effects":
        from ..effects.presets import normalize_data
        data = normalize_data(data)
    elif kind == "sequence":
        data = {"tokens": [str(t) for t in data.get("tokens", [])]}
    return Preset(kind, str(raw.get("name", "Untitled")), data, str(raw.get("description", "")),
                  created=str(raw.get("created", "")))
