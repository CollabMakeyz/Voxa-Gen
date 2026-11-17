import json

import numpy as np
import pytest
import soundfile as sf

from voxagen.core.audio.generation import render_generation
from voxagen.core.audio.pipeline import Cancelled, plan_notes
from voxagen.core.export.exporter import (
    ExportConflict, ExportError, export_chromatic, unique_destination, validate_template,
)
from voxagen.core.export.riff import WavWriter, parse_wav
from voxagen.core.pitch.detect import median_f0
from voxagen.core.pitch.tuning import cents_between
from voxagen.core.samples.library import SampleLibrary
from voxagen.models.config import GeneratorConfig


@pytest.fixture
def lib(make_wav):
    l = SampleLibrary()
    for name, f0 in [("a.wav", 220), ("e.wav", 247), ("a2.wav", 233)]:
        l.add_files([make_wav(name, f0=f0, dur=0.4)])
    return l


def _cfg(**export):
    c = GeneratorConfig()
    c.mode = "robot"
    c.musical.start_note, c.musical.start_octave, c.musical.semitones = 0, 3, 5
    for k, v in export.items():
        setattr(c.export, k, v)
    return c


def test_riff_writer_markers_roundtrip(tmp_path):
    p = tmp_path / "m.wav"
    with WavWriter(p, 44100, 2, "pcm24") as w:
        w.add_marker(0, "C3")
        w.write(np.zeros((1001, 2)))
        w.add_marker(1001, "C#3")
        w.write(np.full((500, 2), 0.25))
    info = parse_wav(p)
    assert info.riff_size_ok and info.frames == 1501 and info.bits == 24 and info.channels == 2
    assert info.cues == [(1, 0), (2, 1001)] and info.labels == {1: "C3", 2: "C#3"}
    data, sr = sf.read(p)
    assert sr == 44100 and data.shape == (1501, 2) and abs(data[-1, 0] - 0.25) < 1e-5


@pytest.mark.parametrize("bit_depth,channels", [("pcm16", "mono"), ("pcm24", "stereo"), ("float32", "mono")])
def test_export_full(lib, tmp_path, bit_depth, channels):
    cfg = _cfg(bit_depth=bit_depth, channels=channels, sample_rate=44100, gap_ms=120, fade_in_ms=5, fade_out_ms=20)
    dest = tmp_path / "out" / "Voxa GEN Export"
    res = export_chromatic(cfg, lib, dest)
    assert res.validation.ok, res.validation.failures
    info = parse_wav(res.chromatic)
    assert info.sample_rate == 44100 and info.channels == (2 if channels == "stereo" else 1)
    assert len(info.cues) == 5
    starts = [n["start_frame"] for n in json.loads(res.info_file.read_text())["notes"]]
    assert [c[1] for c in info.cues] == starts
    assert len(res.notes) == 5 and all(p.exists() for p in res.notes)
    assert res.notes[0].name == "note_001.wav"
    assert not [p for p in (tmp_path / "out").iterdir() if p.name.startswith(".voxagen-tmp")]
    data, sr = sf.read(res.chromatic, always_2d=True)
    for i, start in enumerate(starts[:3]):
        n = res.generation.notes[i].frames
        f = median_f0(data[start:start + n], sr)
        assert abs(cents_between(f, res.generation.notes[i].plan.target_hz)) < 5


def test_marker_positions_include_gap(lib, tmp_path):
    cfg = _cfg(gap_ms=250, fixed_duration=True, fixed_duration_ms=500, sample_rate=48000)
    res = export_chromatic(cfg, lib, tmp_path / "x")
    pos = [c[1] for c in parse_wav(res.chromatic).cues]
    step = 24000 + 12000
    assert pos == [i * step for i in range(5)]
    assert parse_wav(res.chromatic).frames == 5 * 24000 + 4 * 12000


def test_conflict_never_overwrites_silently(lib, tmp_path):
    cfg = _cfg()
    dest = tmp_path / "exp"
    export_chromatic(cfg, lib, dest)
    before = (dest / "chromatic.wav").read_bytes()
    with pytest.raises(ExportConflict) as ei:
        export_chromatic(cfg, lib, dest)
    assert ei.value.conflicts
    assert (dest / "chromatic.wav").read_bytes() == before
    assert unique_destination(dest).name == "exp (2)"
    res = export_chromatic(cfg, lib, dest, overwrite=True)
    assert res.validation.ok


def test_cancel_leaves_nothing(lib, tmp_path):
    cfg = _cfg()
    calls = {"n": 0}

    def cancel():
        calls["n"] += 1
        return calls["n"] > 3

    with pytest.raises(Cancelled):
        export_chromatic(cfg, lib, tmp_path / "c" / "dest", cancel=cancel)
    assert not (tmp_path / "c" / "dest").exists()
    assert list((tmp_path / "c").iterdir()) == []


def test_global_normalization_and_master_volume(lib, tmp_path):
    cfg = _cfg(normalize=True, normalize_peak_db=-1.0, bit_depth="float32")
    res = export_chromatic(cfg, lib, tmp_path / "n")
    data, _ = sf.read(res.chromatic)
    assert 20 * np.log10(np.max(np.abs(data))) == pytest.approx(-1.0, abs=0.05)
    cfg = _cfg(normalize=True, normalize_peak_db=-1.0, master_volume_db=12.0, bit_depth="pcm16")
    res = export_chromatic(cfg, lib, tmp_path / "m")
    data, _ = sf.read(res.chromatic)
    assert np.max(np.abs(data)) < 1.0 and res.generation.gains.clip_protected
    assert any("Clip protection" in w for w in res.warnings)


def test_normalization_off_is_not_applied(lib):
    cfg = _cfg(normalize=False)
    gen = render_generation(cfg, lib)
    assert gen.gains.gain == pytest.approx(1.0)


def test_fixed_duration_pad_only_never_trims(lib):
    cfg = _cfg(fixed_duration=True, fixed_duration_ms=100, fit_mode="pad_only")
    gen = render_generation(cfg, lib)
    assert all(n.frames == int(0.4 * 48000) for n in gen.notes)
    cfg = _cfg(fixed_duration=True, fixed_duration_ms=100, fit_mode="pad_trim")
    assert all(n.frames == 4800 for n in render_generation(cfg, lib).notes)


def test_stretch_mode_reaches_target(lib):
    cfg = _cfg(fixed_duration=True, fixed_duration_ms=700, fit_mode="stretch")
    gen = render_generation(cfg, lib)
    assert all(n.frames == int(0.7 * 48000) for n in gen.notes)


@pytest.mark.parametrize("mode", ["natural", "robot", "legacy"])
def test_all_modes_export(lib, tmp_path, mode):
    cfg = _cfg(sample_rate=96000)
    cfg.mode = mode
    res = export_chromatic(cfg, lib, tmp_path / mode)
    assert res.validation.ok
    assert json.loads(res.info_file.read_text())["mode"] == mode


def test_vocal_sequence_order_used_in_export(lib, tmp_path):
    cfg = _cfg()
    cfg.order.mode = "vocal"
    cfg.order.sequence = ["e", "a2", "a"]
    plans = plan_notes(cfg, lib)
    assert [p.sample_id for p in plans] == ["e", "a2", "a", "e", "a2"]
    cfg.order.sequence = ["e", "u"]
    with pytest.raises(Exception) as ei:
        export_chromatic(cfg, lib, tmp_path / "v")
    assert "u.wav" in str(ei.value)
    assert not (tmp_path / "v").exists()


def test_templates():
    assert validate_template("note_{index:03d}") is None
    assert validate_template("{pitch}{octave}_{sample}") is None
    assert validate_template("{bogus}") is not None


def test_template_duplicates_rejected(lib, tmp_path):
    cfg = _cfg(note_name_template="{sample}")
    with pytest.raises(ExportError):
        export_chromatic(cfg, lib, tmp_path / "d")


def test_custom_sample_rate(lib, tmp_path):
    res = export_chromatic(_cfg(sample_rate=22050), lib, tmp_path / "sr")
    assert parse_wav(res.chromatic).sample_rate == 22050 and res.validation.ok


def test_original_samples_untouched(lib, tmp_path):
    before = {s.id: open(s.path, "rb").read() for s in lib.samples()}
    export_chromatic(_cfg(), lib, tmp_path / "u")
    assert before == {s.id: open(s.path, "rb").read() for s in lib.samples()}


@pytest.mark.parametrize("mode", ["natural", "robot"])
def test_parallel_render_is_bit_identical(lib, tmp_path, monkeypatch, mode):
    from voxagen.core.audio.pipeline import clear_memory_caches
    cfg = _cfg(bit_depth="pcm24", dither=False, write_individual=True)
    cfg.mode = mode
    cfg.musical.semitones = 8
    out = {}
    for threads in ("1", "4"):
        monkeypatch.setenv("VOXAGEN_RENDER_THREADS", threads)
        monkeypatch.setenv("VOXAGEN_CACHE_DIR", str(tmp_path / f"cache{threads}"))
        clear_memory_caches()
        res = export_chromatic(cfg, lib, tmp_path / f"out{threads}")
        out[threads] = [sf.read(p, dtype="float32")[0] for p in [res.chromatic, *res.notes]]
    assert len(out["1"]) == len(out["4"])
    for a, b in zip(out["1"], out["4"]):
        assert a.shape == b.shape and np.array_equal(a, b)


def test_parallel_render_reports_the_first_failing_note(lib, tmp_path, monkeypatch):
    from voxagen.core.audio import pipeline
    cfg = _cfg()
    cfg.musical.semitones = 6
    real = pipeline.NoteRenderer.render_raw

    def broken(self, plan):
        if plan.index in (2, 4):
            raise ValueError("boom")
        return real(self, plan)
    monkeypatch.setattr(pipeline.NoteRenderer, "render_raw", broken)
    monkeypatch.setenv("VOXAGEN_RENDER_THREADS", "4")
    with pytest.raises(RuntimeError, match=r"^Note 3 "):
        export_chromatic(cfg, lib, tmp_path / "x")
    assert not (tmp_path / "x").exists()


def test_float32_export_with_clip_protection_passes_validation(lib, tmp_path):
    cfg = _cfg(bit_depth="float32", master_volume_db=12.0, prevent_clipping=True)
    res = export_chromatic(cfg, lib, tmp_path / "loud")
    assert res.validation.ok, res.validation.failures
    data, _ = sf.read(res.chromatic, dtype="float32")
    assert np.max(np.abs(data)) <= 1.0
