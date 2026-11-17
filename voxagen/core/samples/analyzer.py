from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable

import numpy as np

from ...i18n import tr
from ..audio.dsp import load_audio
from .library import SampleInfo, SampleLibrary

SEVERITIES = ("error", "warn", "info")


@dataclass
class SampleStats:
    id: str
    peak_db: float = -120.0
    rms_db: float = -120.0
    lead_ms: float = 0.0
    tail_ms: float = 0.0
    silent_ratio: float = 0.0
    clipped: int = 0
    dc_offset: float = 0.0
    duration: float = 0.0
    sample_rate: int = 0
    channels: int = 0
    format: str = ""


def _m(template: str, **values) -> tuple:
    return (template, values)


@dataclass
class Finding:
    sample_id: str
    severity: str
    kind: str
    msg: tuple
    fix_msg: tuple

    @property
    def message(self) -> str:
        return tr(self.msg[0], **self.msg[1])

    @property
    def fix(self) -> str:
        return tr(self.fix_msg[0], **self.fix_msg[1])


@dataclass
class AnalysisReport:
    stats: dict[str, SampleStats] = field(default_factory=dict)
    findings: list[Finding] = field(default_factory=list)

    def for_sample(self, sid: str) -> list[Finding]:
        return [f for f in self.findings if f.sample_id == sid]

    def count(self, severity: str) -> int:
        return sum(1 for f in self.findings if f.severity == severity)

    @property
    def ok(self) -> bool:
        return self.count("error") == 0


SILENCE_DB = -50.0


def _db(v: float) -> float:
    return 20.0 * float(np.log10(max(v, 1e-6)))


def measure(info: SampleInfo) -> SampleStats:
    x, sr = load_audio(info.path)
    st = SampleStats(info.id, duration=len(x) / sr if sr else 0.0, sample_rate=sr, channels=x.shape[1],
                     format=info.bit_depth_label)
    if len(x) == 0:
        return st
    mono = x.mean(axis=1)
    st.peak_db = _db(float(np.max(np.abs(x))))
    st.dc_offset = float(np.mean(mono))
    hop = max(1, int(sr * 0.01))
    frames = len(mono) // hop
    if frames:
        rms = np.sqrt(np.mean(mono[: frames * hop].reshape(frames, hop) ** 2, axis=1))
        db = 20 * np.log10(np.maximum(rms, 1e-9))
        loud = db > SILENCE_DB
        st.silent_ratio = float(1.0 - loud.mean())
        if loud.any():
            first, last = int(np.argmax(loud)), int(len(loud) - 1 - np.argmax(loud[::-1]))
            st.lead_ms = first * 10.0
            st.tail_ms = (len(loud) - 1 - last) * 10.0
            st.rms_db = _db(float(np.sqrt(np.mean(rms[loud] ** 2))))
        else:
            st.lead_ms = st.duration * 1000.0
    full = np.abs(x) >= 0.999
    if full.any():
        for c in range(x.shape[1]):
            col = full[:, c].astype(np.int8)
            edges = np.diff(np.concatenate([[0], col, [0]]))
            starts, ends = np.where(edges == 1)[0], np.where(edges == -1)[0]
            st.clipped += int(np.sum((ends - starts)[(ends - starts) >= 3]))
    return st


def analyze_library(library: SampleLibrary, disabled: set[str] | None = None,
                    progress: Callable[[str, int, int, str], None] | None = None,
                    cancel: Callable[[], bool] | None = None) -> AnalysisReport:
    rep = AnalysisReport()
    disabled = disabled or set()
    samples = library.samples()
    add = rep.findings.append
    for i, s in enumerate(samples):
        if cancel and cancel():
            from ..audio.pipeline import Cancelled
            raise Cancelled()
        if progress:
            progress("analyze", i, len(samples), s.id)
        if s.status == "missing":
            add(Finding(s.id, "error", "missing", _m("The file is missing: {path}", path=s.path),
                        _m("Locate the file again or remove the sample from the list.")))
            continue
        if s.status != "ok":
            add(Finding(s.id, "error", "invalid", _m("The file cannot be read: {error}", error=s.error),
                        _m("Export it again as a WAV file from your audio editor.")))
            continue
        try:
            st = measure(s)
        except Exception as exc:
            add(Finding(s.id, "error", "invalid", _m("The file cannot be read: {error}", error=s_m(exc)),
                        _m("Export it again as a WAV file from your audio editor.")))
            continue
        rep.stats[s.id] = st
        if st.rms_db <= -119:
            add(Finding(s.id, "error", "silent", _m("The sample is silent (nothing above {db} dB).", db=int(SILENCE_DB)),
                        _m("Check the recording; a silent sample makes silent notes.")))
            continue
        if st.clipped:
            add(Finding(s.id, "warn", "clipping",
                        _m("Clipping: {count} samples hit full scale.", count=st.clipped),
                        _m("Record or export it a little quieter. Clipping turns into harsh distortion after retuning.")))
        if st.lead_ms > 150 or st.tail_ms > 300 or st.silent_ratio > 0.45:
            add(Finding(s.id, "warn", "silence",
                        _m("Lots of silence: {lead} ms before and {tail} ms after the voice ({pct} % of the file).",
                           lead=int(st.lead_ms), tail=int(st.tail_ms), pct=int(round(st.silent_ratio * 100))),
                        _m("Turn on 'Trim silence' in Exporting, or trim the file. Notes will start on time.")))
        if st.duration < 0.08:
            add(Finding(s.id, "warn", "short", _m("Very short sample ({ms} ms).", ms=int(st.duration * 1000)),
                        _m("Pitch is hard to detect in very short sounds; use a longer take if you can.")))
        if abs(st.dc_offset) > 0.02:
            add(Finding(s.id, "info", "dc", _m("DC offset of {pct} %.", pct=round(st.dc_offset * 100, 1)),
                        _m("Usually harmless; the EQ's low cut removes it.")))
        if s.duplicate_of:
            add(Finding(s.id, "info", "duplicate", _m("Same audio as '{other}'.", other=s.duplicate_of),
                        _m("Remove one of them if the duplicate was not intended.")))
    if progress:
        progress("analyze", len(samples), len(samples), "")
    _compare(rep, [s for s in samples if s.id in rep.stats and s.id not in disabled])
    order = {"error": 0, "warn": 1, "info": 2}
    rep.findings.sort(key=lambda f: (order.get(f.severity, 3), f.sample_id == "", f.sample_id))
    return rep


def _compare(rep: AnalysisReport, samples: list[SampleInfo]) -> None:
    stats = [rep.stats[s.id] for s in samples if rep.stats[s.id].rms_db > -119]
    if len(stats) < 2:
        return
    add = rep.findings.append
    loud = np.array([st.rms_db for st in stats])
    med = float(np.median(loud))
    for st in stats:
        diff = st.rms_db - med
        if abs(diff) >= 6.0:
            add(Finding(st.id, "warn", "volume",
                        _m("{diff} dB louder than the other samples." if diff > 0 else
                           "{diff} dB quieter than the other samples.", diff=round(abs(diff), 1)),
                        _m('Turn on Normalize per note in Exporting, or level the files. Every note will come out equally loud.')))
    durs = np.array([st.duration for st in stats])
    dmed = float(np.median(durs))
    for st in stats:
        if dmed > 0 and (st.duration > dmed * 2.0 or st.duration < dmed * 0.5):
            add(Finding(st.id, "warn", "duration",
                        _m("Duration {sec} s is very different from the others (typical {typ} s).",
                           sec=round(st.duration, 2), typ=round(dmed, 2)),
                        _m("Use 'Same length for every note' in Exporting, or trim the file.")))
    rates = sorted({st.sample_rate for st in stats})
    if len(rates) > 1:
        add(Finding("", "info", "rates", _m("Mixed sample rates: {rates}.", rates=", ".join(f"{r} Hz" for r in rates)),
                    _m("Fine: everything is converted to the export rate with high-quality resampling.")))
    chans = sorted({st.channels for st in stats})
    if len(chans) > 1:
        add(Finding("", "info", "channels", _m("Mono and stereo files are mixed."),
                    _m("Fine: they are converted to the export channel layout.")))
