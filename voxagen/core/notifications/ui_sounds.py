from __future__ import annotations

import threading
from pathlib import Path

import numpy as np
import soundfile as sf
from PySide6.QtCore import QIODevice, QObject
from PySide6.QtMultimedia import QAudioSink

from ...models.app_settings import UI_SOUND_EVENTS, UiSoundSettings
from ...paths import assets_dir
from ..preview.output import encode, output_format, to_device

BUILTIN_DIR = "sounds/fnf"
MAX_VOICES = 8
MAX_SOUND_SECONDS = 5.0


def builtin_sounds() -> list[str]:
    d = assets_dir() / BUILTIN_DIR
    return sorted({p.stem for p in d.glob("*.ogg")} | {p.stem for p in d.glob("*.mp3")}, key=str.lower)


def resolve_source(source: str) -> Path | None:
    if not source:
        return None
    d = assets_dir() / BUILTIN_DIR
    for ext in (".ogg", ".mp3", ".wav"):
        p = d / f"{source}{ext}"
        if p.exists():
            return p
    p = Path(source)
    return p if p.exists() else None


def validate_user_sound(path: str | Path) -> str | None:
    try:
        info = sf.info(str(path))
    except Exception as exc:
        return f"Unsupported or unreadable audio file ({exc})."
    if info.frames / max(info.samplerate, 1) > MAX_SOUND_SECONDS:
        return f"Interface sounds must be at most {MAX_SOUND_SECONDS:.0f} seconds long."
    return None


class _Mixer(QIODevice):
    def __init__(self, engine: "UiSoundEngine"):
        super().__init__()
        self.e = engine

    def readData(self, maxlen):
        return self.e._mix(maxlen)

    def writeData(self, data):
        return 0

    def bytesAvailable(self):
        return 1 << 15

    def isSequential(self):
        return True


class UiSoundEngine(QObject):
    def __init__(self, settings: UiSoundSettings, parent=None):
        super().__init__(parent)
        self.settings = settings
        self._cache: dict[str, np.ndarray] = {}
        self._voices: list[list] = []
        self._lock = threading.Lock()
        self._round_robin = 0
        try:
            self.dev, self.fmt = output_format()
            self._sink = QAudioSink(self.dev, self.fmt, self)
            self._sink.setBufferSize(int(self.fmt.sampleRate() * 2 * 4 * 0.04))
            self._io = _Mixer(self)
            self._io.open(QIODevice.OpenModeFlag.ReadOnly)
            self._started = False
            self.available = True
        except Exception:
            self.available = False

    def _load(self, source: str) -> np.ndarray | None:
        if source in self._cache:
            return self._cache[source]
        path = resolve_source(source)
        if path is None:
            return None
        try:
            data, sr = sf.read(str(path), dtype="float64", always_2d=True)
            buf = to_device(data[: int(sr * MAX_SOUND_SECONDS)], sr, self.fmt)
        except Exception:
            return None
        self._cache[source] = buf
        return buf

    def invalidate(self, source: str | None = None) -> None:
        if source is None:
            self._cache.clear()
        else:
            self._cache.pop(source, None)

    def play(self, event_id: str, force: bool = False) -> None:
        if not self.available:
            return
        s = self.settings
        ev = s.event(event_id)
        if not force and (not s.enabled or not ev.enabled):
            return
        source = ev.source
        if event_id == "keyboard" and source == UI_SOUND_EVENTS["keyboard"][0]:
            source = ("keyboard1", "keyboard2", "keyboard3")[self._round_robin % 3]
            self._round_robin += 1
        self.play_source(source, ev.volume)

    def play_source(self, source: str, volume: float = 1.0) -> None:
        if not self.available:
            return
        buf = self._load(source)
        if buf is None:
            return
        gain = float(np.clip(volume, 0, 1)) * float(np.clip(self.settings.master_volume, 0, 1))
        if gain <= 0:
            return
        with self._lock:
            self._voices.append([buf, 0, gain])
            if len(self._voices) > MAX_VOICES:
                self._voices.pop(0)
        if not self._started:
            self._sink.start(self._io)
            self._started = True

    def _mix(self, maxlen: int) -> bytes:
        bps = 2 if self.fmt.sampleFormat() == self.fmt.SampleFormat.Int16 else 4
        frames = maxlen // (2 * bps)
        if frames <= 0:
            return b""
        out = np.zeros((frames, 2), dtype=np.float32)
        with self._lock:
            alive = []
            for v in self._voices:
                buf, pos, g = v
                n = min(frames, len(buf) - pos)
                if n > 0:
                    out[:n] += buf[pos:pos + n] * g
                    v[1] = pos + n
                if v[1] < len(buf):
                    alive.append(v)
            self._voices = alive
        return encode(out, self.fmt)
