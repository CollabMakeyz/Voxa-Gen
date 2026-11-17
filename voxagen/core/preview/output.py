from __future__ import annotations

import numpy as np
from PySide6.QtMultimedia import QAudioDevice, QAudioFormat, QMediaDevices

from ..audio.dsp import as_2d, conform_channels, resample


def output_format(device: QAudioDevice | None = None) -> tuple[QAudioDevice, QAudioFormat]:
    dev = device or QMediaDevices.defaultAudioOutput()
    fmt = QAudioFormat()
    pref = dev.preferredFormat()
    sr = pref.sampleRate() if pref.sampleRate() > 0 else 48000
    fmt.setSampleRate(sr)
    fmt.setChannelCount(2)
    fmt.setSampleFormat(QAudioFormat.SampleFormat.Float)
    if not dev.isFormatSupported(fmt):
        fmt.setSampleFormat(QAudioFormat.SampleFormat.Int16)
    return dev, fmt


def to_device(x: np.ndarray, sr: int, fmt: QAudioFormat) -> np.ndarray:
    y = conform_channels(as_2d(x), 2)
    if sr != fmt.sampleRate():
        y = resample(y, sr, fmt.sampleRate(), "hq")
    return np.ascontiguousarray(y, dtype=np.float32)


def encode(block: np.ndarray, fmt: QAudioFormat) -> bytes:
    if fmt.sampleFormat() == QAudioFormat.SampleFormat.Int16:
        return (np.clip(block, -1, 1) * 32767).astype("<i2").tobytes()
    return np.clip(block, -1, 1).astype("<f4").tobytes()
