from __future__ import annotations

import threading

import numpy as np
from PySide6.QtCore import QIODevice, QObject, QTimer, Signal
from PySide6.QtMultimedia import QAudio, QAudioSink

from ..audio.dsp import active_rms
from .output import encode, output_format, to_device


class _Source(QIODevice):
    def __init__(self, player: "PreviewPlayer"):
        super().__init__()
        self.p = player

    def readData(self, maxlen: int):
        return self.p._pull(maxlen)

    def writeData(self, data):
        return 0

    def bytesAvailable(self) -> int:
        return 1 << 16

    def isSequential(self) -> bool:
        return True


class PreviewPlayer(QObject):
    positionChanged = Signal(float)
    stateChanged = Signal(str)
    variantChanged = Signal(str)
    loaded = Signal(float)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.dev, self.fmt = output_format()
        self.sr = self.fmt.sampleRate()
        self._variants: dict[str, np.ndarray] = {}
        self._gains: dict[str, float] = {}
        self._active = ""
        self._pos = 0
        self._lock = threading.Lock()
        self.volume = 0.8
        self.loop = False
        self.match_loudness = True
        self.range: tuple[int, int] | None = None
        self.state = "stopped"
        self._sink: QAudioSink | None = None
        self._io = _Source(self)
        self._io.open(QIODevice.OpenModeFlag.ReadOnly)
        self._timer = QTimer(self)
        self._timer.setInterval(30)
        self._timer.timeout.connect(self._tick)
        self._ended = False

    def load(self, variants: dict[str, np.ndarray], sr: int, active: str | None = None,
             keep_position: bool = False) -> None:
        conv = {name: to_device(x, sr, self.fmt) for name, x in variants.items() if x is not None and len(x)}
        gains = {name: 1.0 for name in conv}
        if self.match_loudness and len(conv) > 1:
            ref_name = next(iter(conv))
            ref = active_rms(conv[ref_name], self.sr)
            for name, x in conv.items():
                r = active_rms(x, self.sr)
                gains[name] = float(np.clip(ref / r, 0.125, 8.0)) if r > 0 and ref > 0 else 1.0
        with self._lock:
            self._variants = conv
            self._gains = gains
            if active in conv:
                self._active = active
            elif self._active not in conv:
                self._active = next(iter(conv), "")
            if not keep_position:
                self._pos = 0
            self._pos = min(self._pos, self.length_frames)
            self.range = None
        self.loaded.emit(self.duration)
        self.positionChanged.emit(self.position)

    def clear(self) -> None:
        self.stop()
        with self._lock:
            self._variants = {}
            self._active = ""
        self.loaded.emit(0.0)

    def variants(self) -> list[str]:
        return list(self._variants)

    @property
    def active(self) -> str:
        return self._active

    def set_variant(self, name: str) -> None:
        if name in self._variants and name != self._active:
            with self._lock:
                self._active = name
                self._pos = min(self._pos, self.length_frames)
            self.variantChanged.emit(name)

    @property
    def length_frames(self) -> int:
        x = self._variants.get(self._active)
        return 0 if x is None else len(x)

    @property
    def duration(self) -> float:
        return self.length_frames / float(self.sr)

    @property
    def position(self) -> float:
        pos = self._pos
        if self.state == "playing" and self._sink is not None:
            bps = 2 if self.fmt.sampleFormat() == self.fmt.SampleFormat.Int16 else 4
            queued = max(0, self._sink.bufferSize() - self._sink.bytesFree()) // (2 * bps)
            pos = max(self._start(), pos - queued)
        return pos / float(self.sr)

    def has_audio(self) -> bool:
        return self.length_frames > 0

    def play(self) -> None:
        if not self.has_audio():
            return
        if self.state == "paused" and self._sink is not None:
            self._sink.resume()
        else:
            if self._pos >= self._end():
                self._pos = self._start()
            self._ensure_sink()
            self._sink.start(self._io)
        self._ended = False
        self.state = "playing"
        self._timer.start()
        self.stateChanged.emit(self.state)

    def pause(self) -> None:
        if self.state == "playing" and self._sink is not None:
            self._sink.suspend()
            self.state = "paused"
            self._timer.stop()
            self.stateChanged.emit(self.state)

    def toggle(self) -> None:
        self.pause() if self.state == "playing" else self.play()

    def stop(self) -> None:
        if self._sink is not None:
            self._sink.stop()
        with self._lock:
            self._pos = self._start()
        self.state = "stopped"
        self._timer.stop()
        self.stateChanged.emit(self.state)
        self.positionChanged.emit(self.position)

    def seek(self, seconds: float) -> None:
        with self._lock:
            self._pos = int(np.clip(seconds * self.sr, 0, self.length_frames))
        self.positionChanged.emit(self.position)

    def play_range(self, start_s: float, end_s: float) -> None:
        self.stop()
        self.range = (int(start_s * self.sr), int(end_s * self.sr))
        self._pos = self.range[0]
        self.play()

    def clear_range(self) -> None:
        self.range = None

    def set_volume(self, v: float) -> None:
        self.volume = float(np.clip(v, 0.0, 1.0))

    def _start(self) -> int:
        return self.range[0] if self.range else 0

    def _end(self) -> int:
        return min(self.range[1], self.length_frames) if self.range else self.length_frames

    def _ensure_sink(self) -> None:
        if self._sink is None:
            self._sink = QAudioSink(self.dev, self.fmt, self)
            self._sink.setBufferSize(int(self.sr * 2 * 4 * 0.08))
            self._sink.stateChanged.connect(self._on_sink_state)

    def _pull(self, maxlen: int) -> bytes:
        bps = 4 if self.fmt.sampleFormat() != self.fmt.SampleFormat.Int16 else 2
        frames = max(0, maxlen // (2 * bps))
        if frames == 0:
            return b""
        with self._lock:
            x = self._variants.get(self._active)
            out = np.zeros((frames, 2), dtype=np.float32)
            if x is not None and self.state == "playing":
                end = self._end()
                got = 0
                while got < frames:
                    n = min(frames - got, end - self._pos)
                    if n <= 0:
                        if self.loop:
                            self._pos = self._start()
                            continue
                        self._ended = True
                        break
                    out[got:got + n] = x[self._pos:self._pos + n]
                    got += n
                    self._pos += n
                out *= self.volume * self._gains.get(self._active, 1.0)
        return encode(out, self.fmt)

    def _tick(self) -> None:
        self.positionChanged.emit(self.position)
        if self._ended and self.state == "playing":
            self._ended = False
            if self._sink is not None:
                self._sink.stop()
            self.state = "stopped"
            self._timer.stop()
            with self._lock:
                self._pos = self._start()
            self.stateChanged.emit(self.state)
            self.positionChanged.emit(self.position)

    def _on_sink_state(self, state) -> None:
        if state == QAudio.State.StoppedState and self._sink is not None and self._sink.error() != QAudio.Error.NoError:
            self.state = "stopped"
            self._timer.stop()
            self.stateChanged.emit(self.state)
