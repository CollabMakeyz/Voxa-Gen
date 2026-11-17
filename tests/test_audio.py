import time

import numpy as np
import pytest

from conftest import synth_vowel
from voxagen.core.audio import dsp
from voxagen.core.audio.engines import get_engine
from voxagen.core.pitch.detect import detect_pitch, median_f0
from voxagen.core.pitch.tuning import cents_between, frequency_of, midi_of, note_name
from voxagen.models.config import GeneratorConfig

SR = 48000
TOL_CENTS = 5.0


def _render(mode, x, target, cfg=None, sr=SR, ratio=1.0):
    cfg = cfg or GeneratorConfig()
    eng = get_engine(mode, cfg)
    return eng.render(eng.analyze(x, sr), x, sr, target, ratio)


def test_tuning_reference():
    assert note_name(60) == "C4" and note_name(69) == "A4"
    assert midi_of(0, 4) == 60
    assert frequency_of(69) == pytest.approx(440.0)
    assert frequency_of(69, 432.0) == pytest.approx(432.0)
    assert frequency_of(60) == pytest.approx(261.6256, abs=1e-3)
    assert cents_between(frequency_of(64, temperament="just", root=0), frequency_of(64)) == pytest.approx(-13.69, abs=0.01)


@pytest.mark.parametrize("mode", ["natural", "robot", "legacy", "lab"])
@pytest.mark.parametrize("target", [73.42, 146.83, 261.63, 523.25])
def test_pitch_accuracy(mode, target):
    x = synth_vowel(220.0, SR, 0.9, vibrato_cents=25)
    out = _render(mode, x, target)
    f = median_f0(out.audio, out.sr)
    assert f > 0, "pitch not detectable in output"
    assert abs(cents_between(f, target)) < TOL_CENTS


def test_natural_preserves_duration_and_robot_too():
    x = synth_vowel(200.0, SR, 0.73)
    for mode in ("natural", "robot"):
        out = _render(mode, x, 330.0)
        assert out.sr == SR and len(out.audio) == len(x)
    leg = _render("legacy", x, 330.0)
    assert abs(len(leg.audio) / leg.sr - len(x) / SR) < 0.01


def test_stretch_changes_duration():
    x = synth_vowel(200.0, SR, 0.5)
    out = _render("natural", x, 200.0, ratio=1.6)
    assert len(out.audio) == int(round(len(x) * 1.6))
    f = median_f0(out.audio, out.sr)
    assert abs(cents_between(f, 200.0)) < TOL_CENTS


def _formants(x, sr):
    import parselmouth
    m = dsp.to_mono(x)[:, 0]
    snd = parselmouth.Sound(m, sampling_frequency=sr)
    fm = snd.to_formant_burg(max_number_of_formants=5, maximum_formant=5500)
    t = np.linspace(0.25, 0.75, 40) * snd.duration
    return [float(np.nanmedian([fm.get_value_at_time(k, ti) for ti in t])) for k in (1, 2, 3, 4)]


def _has_near(values, f, tol=0.12):
    return any(abs(v - f) / f < tol for v in values)


def test_formant_preservation():
    x = synth_vowel(150.0, SR, 0.9, formants=((700, 80), (1220, 90), (2600, 120)))
    ratio = 2 ** (7 / 12)
    cfg = GeneratorConfig()
    cfg.natural.formant_preservation = 1.0
    kept = _formants(_render("natural", x, 150.0 * ratio, cfg).audio, SR)
    cfg.natural.formant_preservation = 0.0
    moved = _formants(_render("natural", x, 150.0 * ratio, cfg).audio, SR)
    assert _has_near(kept, 1220) and _has_near(kept, 2600), kept
    assert _has_near(moved, 1220 * ratio) and _has_near(moved, 700 * ratio), moved
    assert not _has_near(moved, 2600, 0.05), moved


def test_stereo_is_preserved_by_natural():
    x = synth_vowel(220.0, SR, 0.6, stereo=True)
    out = _render("natural", x, 300.0)
    assert out.audio.shape[1] == 2
    r = np.sqrt(np.mean(out.audio[:, 1] ** 2)) / np.sqrt(np.mean(out.audio[:, 0] ** 2))
    assert r == pytest.approx(0.6, abs=0.05)


def test_humanization_keeps_target():
    x = synth_vowel(220.0, SR, 1.0, vibrato_cents=40)
    cfg = GeneratorConfig()
    cfg.natural.humanization = 1.0
    cfg.natural.pitch_accuracy = 0.5
    out = _render("natural", x, 300.0, cfg)
    assert abs(cents_between(median_f0(out.audio, SR), 300.0)) < TOL_CENTS


def test_unvoiced_input_is_reported_not_faked():
    rng = np.random.default_rng(0)
    noise = rng.standard_normal(SR // 2) * 0.1
    out = _render("natural", noise, 300.0)
    assert out.warnings and "No voiced" in out.warnings[0]
    info = detect_pitch(noise[:, None], SR)
    assert not info.reliable and info.reason


def test_detect_pitch_reliable_on_vowel():
    x = synth_vowel(196.0, SR, 0.8)
    info = detect_pitch(x[:, None], SR)
    assert info.reliable and info.note == "G3" and abs(info.cents) < 5


def test_robot_is_faster_than_natural():
    x = synth_vowel(220.0, SR, 1.2)
    times = {}
    for mode in ("natural", "robot"):
        eng = get_engine(mode, GeneratorConfig())
        t0 = time.perf_counter()
        a = eng.analyze(x, SR)
        for t in (130.0, 260.0, 390.0):
            eng.render(a, x, SR, t)
        times[mode] = time.perf_counter() - t0
    assert times["robot"] < times["natural"]


def test_fades():
    x = np.ones((1000, 1))
    y = dsp.apply_fades(x, 1000, 100, 200)
    assert y[0, 0] == pytest.approx(0) and y[-1, 0] == pytest.approx(0)
    assert y[500, 0] == 1.0
    assert np.all(np.diff(y[:100, 0]) >= 0)


def test_fit_length_modes():
    x = np.ones((100, 2))
    y, trimmed = dsp.fit_length(x, 150, "pad_trim", 1000)
    assert len(y) == 150 and not trimmed and y[120, 0] == 0
    y, trimmed = dsp.fit_length(x, 50, "pad_trim", 1000)
    assert len(y) == 50 and trimmed
    y, trimmed = dsp.fit_length(x, 50, "pad_only", 1000)
    assert len(y) == 100 and not trimmed


def test_resample_length_and_quality():
    t = np.arange(48000) / 48000
    x = np.sin(2 * np.pi * 1000 * t)[:, None]
    y = dsp.resample(x, 48000, 44100)
    assert abs(len(y) - 44100) <= 1
    f = np.fft.rfftfreq(len(y), 1 / 44100)
    assert abs(f[np.argmax(np.abs(np.fft.rfft(y[:, 0])))] - 1000) < 2


def test_quantize_and_clip():
    x = np.array([[1.5], [-1.5], [0.5]])
    q = dsp.quantize(x, "pcm16", dither=False)
    assert q.dtype == np.dtype("<i2") and q[0, 0] == 32767 and q[1, 0] == -32768
    q24 = dsp.quantize(x, "pcm24", dither=False)
    assert q24[0, 0] == 8388607
    assert dsp.quantize(x, "float32", dither=False).dtype == np.dtype("<f4")


def test_conform_channels():
    st = np.stack([np.ones(10), np.zeros(10)], axis=1)
    assert dsp.conform_channels(st, 1)[0, 0] == 0.5
    assert dsp.conform_channels(np.ones((10, 1)), 2).shape == (10, 2)
