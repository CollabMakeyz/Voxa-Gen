from __future__ import annotations

import struct
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np

from ..audio.dsp import as_2d, quantize

WAVE_FORMAT_PCM = 1
WAVE_FORMAT_IEEE_FLOAT = 3
BYTES_PER_SAMPLE = {"pcm16": 2, "pcm24": 3, "float32": 4}


class WavWriter:
    def __init__(self, path: str | Path, sample_rate: int, channels: int, bit_depth: str,
                 dither: bool = True, seed: int | None = None):
        if bit_depth not in BYTES_PER_SAMPLE:
            raise ValueError(f"Unsupported bit depth {bit_depth}")
        if not (1 <= channels <= 2):
            raise ValueError("Only mono and stereo are supported")
        if not (8000 <= sample_rate <= 384000):
            raise ValueError(f"Invalid sample rate {sample_rate}")
        self.path = Path(path)
        self.sr = int(sample_rate)
        self.ch = int(channels)
        self.bit_depth = bit_depth
        self.dither = dither
        self.rng = np.random.default_rng(seed)
        self.bps = BYTES_PER_SAMPLE[bit_depth]
        self.frames = 0
        self.markers: list[tuple[int, str]] = []
        self._fh = open(self.path, "wb")
        self._closed = False
        self._write_header()

    def _write_header(self) -> None:
        f = self._fh
        f.write(b"RIFF\x00\x00\x00\x00WAVE")
        is_float = self.bit_depth == "float32"
        fmt_tag = WAVE_FORMAT_IEEE_FLOAT if is_float else WAVE_FORMAT_PCM
        block = self.ch * self.bps
        fmt = struct.pack("<HHIIHH", fmt_tag, self.ch, self.sr, self.sr * block, block, self.bps * 8)
        if is_float:
            fmt += struct.pack("<H", 0)
        f.write(b"fmt " + struct.pack("<I", len(fmt)) + fmt)
        self._fact_pos = None
        if is_float:
            f.write(b"fact" + struct.pack("<I", 4))
            self._fact_pos = f.tell()
            f.write(struct.pack("<I", 0))
        f.write(b"data")
        self._data_size_pos = f.tell()
        f.write(b"\x00\x00\x00\x00")
        self._data_start = f.tell()

    def write(self, x: np.ndarray) -> None:
        x = as_2d(x)
        if x.shape[1] != self.ch:
            raise ValueError(f"Expected {self.ch} channels, got {x.shape[1]}")
        q = quantize(x, self.bit_depth, self.dither, self.rng)
        if self.bit_depth == "pcm24":
            raw = np.ascontiguousarray(q.astype("<i4")).view(np.uint8).reshape(-1, 4)[:, :3].tobytes()
        else:
            raw = np.ascontiguousarray(q).tobytes()
        self._fh.write(raw)
        self.frames += len(x)

    def write_silence(self, frames: int, block: int = 65536) -> None:
        while frames > 0:
            n = min(frames, block)
            self.write(np.zeros((n, self.ch)))
            frames -= n

    def add_marker(self, frame: int, label: str) -> None:
        self.markers.append((int(frame), label))

    def close(self) -> None:
        if self._closed:
            return
        f = self._fh
        data_bytes = f.tell() - self._data_start
        if data_bytes & 1:
            f.write(b"\x00")
        if self.markers:
            n = len(self.markers)
            f.write(b"cue " + struct.pack("<II", 4 + 24 * n, n))
            for i, (pos, _) in enumerate(self.markers, start=1):
                f.write(struct.pack("<II", i, pos) + b"data" + struct.pack("<III", 0, 0, pos))
            labels = b""
            for i, (_, text) in enumerate(self.markers, start=1):
                payload = struct.pack("<I", i) + text.encode("utf-8") + b"\x00"
                labels += b"labl" + struct.pack("<I", len(payload)) + payload + (b"\x00" if len(payload) & 1 else b"")
            f.write(b"LIST" + struct.pack("<I", 4 + len(labels)) + b"adtl" + labels)
        end = f.tell()
        f.seek(4)
        f.write(struct.pack("<I", end - 8))
        f.seek(self._data_size_pos)
        f.write(struct.pack("<I", data_bytes))
        if self._fact_pos is not None:
            f.seek(self._fact_pos)
            f.write(struct.pack("<I", self.frames))
        f.close()
        self._closed = True

    def abort(self) -> None:
        if not self._closed:
            self._fh.close()
            self._closed = True
        try:
            self.path.unlink()
        except OSError:
            pass

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        if exc_type is None:
            self.close()
        else:
            self.abort()


@dataclass
class WavInfo:
    format_tag: int = 0
    channels: int = 0
    sample_rate: int = 0
    bits: int = 0
    block_align: int = 0
    data_bytes: int = 0
    frames: int = 0
    riff_size_ok: bool = False
    chunks: list[str] = field(default_factory=list)
    cues: list[tuple[int, int]] = field(default_factory=list)
    labels: dict[int, str] = field(default_factory=dict)


def parse_wav(path: str | Path) -> WavInfo:
    info = WavInfo()
    data = Path(path).read_bytes()
    if data[:4] != b"RIFF" or data[8:12] != b"WAVE":
        raise ValueError("Not a RIFF/WAVE file")
    riff_size = struct.unpack_from("<I", data, 4)[0]
    info.riff_size_ok = riff_size + 8 == len(data)
    pos = 12
    while pos + 8 <= len(data):
        cid = data[pos:pos + 4]
        size = struct.unpack_from("<I", data, pos + 4)[0]
        body = data[pos + 8: pos + 8 + size]
        name = cid.decode("latin-1")
        info.chunks.append(name)
        if cid == b"fmt ":
            (info.format_tag, info.channels, info.sample_rate, _, info.block_align,
             info.bits) = struct.unpack_from("<HHIIHH", body, 0)
        elif cid == b"data":
            info.data_bytes = size
        elif cid == b"cue ":
            n = struct.unpack_from("<I", body, 0)[0]
            for i in range(n):
                cue_id, position = struct.unpack_from("<II", body, 4 + 24 * i)
                info.cues.append((cue_id, position))
        elif cid == b"LIST" and body[:4] == b"adtl":
            p = 4
            while p + 8 <= len(body):
                sub = body[p:p + 4]
                ssize = struct.unpack_from("<I", body, p + 4)[0]
                if sub == b"labl":
                    cue_id = struct.unpack_from("<I", body, p + 8)[0]
                    text = body[p + 12: p + 8 + ssize].split(b"\x00")[0].decode("utf-8", "replace")
                    info.labels[cue_id] = text
                p += 8 + ssize + (ssize & 1)
        pos += 8 + size + (size & 1)
    if info.block_align:
        info.frames = info.data_bytes // info.block_align
    return info
