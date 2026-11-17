import numpy as np
import pytest

from voxagen.core.effects import EFFECTS, FxContext, apply_chain, chain_key, new_slot
from voxagen.core.effects.presets import BUILTIN_EFFECT_PRESETS, CATEGORIES, chain_from_data, normalize_data
from voxagen.core.history import History
from voxagen.core.pitch.detect import median_f0
from voxagen.core.pitch.tuning import cents_between
from voxagen.models.config import EffectsSettings, GeneratorConfig

from conftest import synth_vowel

SR = 48000


def _sine(hz, dur=1.0, amp=0.5):
    t = np.arange(int(SR * dur)) / SR
    return (amp * np.sin(2 * np.pi * hz * t))[:, None]


def _run(effect, x, ctx=None, **params):
    e = EFFECTS[effect]
    return e.process(x, SR, e.resolve(params), ctx or FxContext(220.0, 3, 0))


def _peak_hz(y):
    spec = np.abs(np.fft.rfft(y[:, 0] * np.hanning(len(y))))
    return np.fft.rfftfreq(len(y), 1 / SR)[np.argmax(spec)]


def _band_energy(y, lo, hi):
    spec = np.abs(np.fft.rfft(y[:, 0])) ** 2
    f = np.fft.rfftfreq(len(y), 1 / SR)
    return spec[(f >= lo) & (f < hi)].sum()


@pytest.fixture(scope="module")
def vowel():
    return synth_vowel(220.0, dur=1.0).astype(np.float64)[:, None]


def test_all_effects_keep_shape_and_are_finite(vowel):
    st = np.repeat(vowel, 2, axis=1)
    for k, e in EFFECTS.items():
        for x in (vowel, st):
            y = e.process(x, SR, e.resolve({}), FxContext(220.0, 1, 0))
            assert y.shape == x.shape, k
            assert np.isfinite(y).all(), k
            assert not np.allclose(y, x), f"{k} did not change the audio"
    assert len(EFFECTS) == 14


def test_every_param_has_help_and_valid_default():
    for e in EFFECTS.values():
        assert len(e.help) > 120 and e.summary
        for p in e.params:
            assert p.help, (e.id, p.key)
            assert p.clamp(p.default) == p.default, (e.id, p.key)


def test_tremolo_changes_volume_not_pitch():
    x = _sine(440)
    y = _run("tremolo", x, rate_hz=5.0, depth=1.0, shape="sine")
    env = np.abs(y[:, 0]).reshape(-1, 480).max(axis=1)
    assert env.max() > 0.45 and env.min() < 0.05
    assert abs(_peak_hz(y) - 440) < 3


def test_vibrato_changes_pitch_periodically_but_keeps_average():
    x = _sine(440, 2.0)
    y = _run("vibrato", x, rate_hz=5.0, depth_cents=100.0, onset_ms=0.0)
    seg = SR // 50
    freqs = []
    for i in range(0, len(y) - seg, seg):
        z = y[i:i + seg, 0]
        zc = np.where(np.diff(np.signbit(z)))[0]
        if len(zc) > 2:
            freqs.append((len(zc) - 1) / 2 / ((zc[-1] - zc[0]) / SR))
    freqs = np.array(freqs[5:-5])
    assert freqs.max() > 440 * 2 ** (60 / 1200) and freqs.min() < 440 * 2 ** (-60 / 1200)
    assert abs(cents_between(float(np.median(freqs)), 440.0)) < 15
    env = np.abs(y[:, 0]).reshape(-1, 960).max(axis=1)[5:-5]
    assert env.min() > 0.45


def test_pitch_variation_is_random_but_seeded_and_centred(vowel):
    a = _run("pitch_variation", vowel, FxContext(220, 5, 0), depth_cents=30, speed_hz=2)
    b = _run("pitch_variation", vowel, FxContext(220, 5, 0), depth_cents=30, speed_hz=2)
    c = _run("pitch_variation", vowel, FxContext(220, 5, 1), depth_cents=30, speed_hz=2)
    assert np.array_equal(a, b)
    assert not np.allclose(a, c)
    assert abs(cents_between(median_f0(a, SR), 220.0)) < 12


def test_formant_shift_moves_timbre_keeps_pitch(vowel):
    up = _run("formant_shift", vowel, shift_st=6.0)
    down = _run("formant_shift", vowel, shift_st=-6.0)
    for y in (up, down):
        assert abs(cents_between(median_f0(y, SR), 220.0)) < 10

    def centroid(y):
        spec = np.abs(np.fft.rfft(y[:, 0]))
        f = np.fft.rfftfreq(len(y), 1 / SR)
        m = (f > 80) & (f < 6000)
        return (spec[m] * f[m]).sum() / spec[m].sum()
    assert centroid(up) > centroid(vowel) * 1.15 > centroid(down) * 1.15


def test_frequency_shifter_moves_by_hertz_not_ratio():
    y = _run("frequency_shifter", _sine(500), shift_hz=200.0)
    assert abs(_peak_hz(y) - 700) < 3
    y2 = _run("frequency_shifter", _sine(1000), shift_hz=200.0)
    assert abs(_peak_hz(y2) - 1200) < 3


def test_double_pitch_adds_octave_below(vowel):
    y = _run("double_pitch", vowel, interval_st=-12, detune_cents=0, level=1.0)
    assert _band_energy(y, 100, 120) > 20 * _band_energy(vowel, 100, 120)
    assert _band_energy(y, 210, 230) > 0.5 * _band_energy(vowel, 210, 230)


def test_ring_modulator_follows_note():
    y = _run("ring_modulator", _sine(300), FxContext(300.0), carrier="note", ratio=2.0, waveform="sine")
    assert _band_energy(y, 890, 910) > 0.2 * _band_energy(y, 0, SR / 2)
    y2 = _run("ring_modulator", _sine(300), FxContext(300.0), carrier="fixed", freq_hz=1000.0)
    assert _band_energy(y2, 1290, 1310) > 0.2 * _band_energy(y2, 0, SR / 2)


def test_bitcrusher_quantizes_and_holds():
    y = _run("bitcrusher", _sine(440), bits=3, rate_hz=8000)
    assert len(np.unique(np.round(y, 6))) <= 2 ** 3 + 1
    assert np.mean(np.diff(y[:, 0]) == 0) > 0.8


def test_eq_boosts_and_cuts_where_asked():
    noise = np.random.default_rng(0).standard_normal((SR, 1)) * 0.1
    y = _run("eq", noise, low_cut_hz=20, mid_freq_hz=2000, mid_gain_db=12, mid_q=2)
    assert _band_energy(y, 1900, 2100) > 8 * _band_energy(noise, 1900, 2100)
    y = _run("eq", noise, low_cut_hz=500, high_cut_hz=20000)
    assert _band_energy(y, 20, 150) < 0.05 * _band_energy(noise, 20, 150)
    flat = _run("eq", noise, low_cut_hz=20, high_cut_hz=20000)
    assert np.allclose(flat, noise)


def test_distortion_adds_harmonics_saturation_keeps_level():
    x = _sine(200)
    d = _run("distortion", x, drive_db=24, type="hard", tone_hz=16000, output_db=0)
    assert _band_energy(d, 590, 610) > 100 * (_band_energy(x, 590, 610) + 1e-9)
    s = _run("saturation", x, drive_db=12)
    assert abs(np.sqrt(np.mean(s ** 2)) / np.sqrt(np.mean(x ** 2)) - 1) < 0.1


def test_chorus_phaser_noise_change_signal(vowel):
    for k in ("chorus", "phaser", "noise"):
        y = _run(k, vowel)
        assert np.sqrt(np.mean((y - vowel) ** 2)) > 0.005, k
    n = _run("noise", np.zeros((SR, 1)) + 1e-9, level_db=-20, follow=1.0)
    assert np.abs(n).max() < 1e-3


def test_chain_off_by_default_and_when_disabled(vowel):
    cfg = GeneratorConfig()
    assert cfg.effects.enabled is False
    fx = EffectsSettings(enabled=False, chain=[new_slot("distortion")])
    assert apply_chain(vowel, SR, fx) is vowel
    assert chain_key(fx) == ""
    fx.enabled = True
    fx.chain[0].enabled = False
    assert chain_key(fx) == ""


def test_chain_order_mix_and_key(vowel):
    a = new_slot("bitcrusher")
    b = new_slot("eq")
    b.params["high_cut_hz"] = 2000.0
    fx1 = EffectsSettings(True, [a, b])
    fx2 = EffectsSettings(True, [b, a])
    assert not np.allclose(apply_chain(vowel, SR, fx1), apply_chain(vowel, SR, fx2))
    assert chain_key(fx1) != chain_key(fx2)
    d = new_slot("distortion")
    d.mix = 0.0
    assert np.allclose(apply_chain(vowel, SR, EffectsSettings(True, [d])), vowel)


def test_pipeline_applies_effects_only_when_enabled(make_wav):
    from voxagen.core.audio.generation import render_generation
    from voxagen.core.samples.library import SampleLibrary
    lib = SampleLibrary()
    lib.add_files([make_wav("a.wav", dur=0.4)])
    cfg = GeneratorConfig()
    cfg.mode = "robot"
    cfg.musical.semitones = 2
    plain = render_generation(cfg, lib).assemble()
    cfg.effects.chain = [new_slot("tremolo")]
    cfg.effects.chain[0].params.update(depth=1.0, rate_hz=10.0)
    assert np.allclose(render_generation(cfg, lib).assemble(), plain)
    cfg.effects.enabled = True
    fx = render_generation(cfg, lib).assemble()
    assert not np.allclose(fx, plain)
    assert np.allclose(render_generation(cfg, lib).assemble(), fx)


def test_builtin_presets_cover_categories_and_render(vowel):
    cats = {c for c, *_ in BUILTIN_EFFECT_PRESETS}
    assert cats == set(CATEGORIES)
    for cat, name, _, slots in BUILTIN_EFFECT_PRESETS:
        chain = chain_from_data({"category": cat, "chain": slots})
        y = apply_chain(vowel[: SR // 4], SR, EffectsSettings(True, chain))
        assert np.isfinite(y).all() and not np.allclose(y, vowel[: SR // 4]), name


def test_effect_preset_manager_roundtrip(tmp_path):
    from voxagen.core.presets.manager import Preset, PresetManager
    pm = PresetManager(tmp_path / "p")
    names = [p.name for p in pm.list("effects")]
    assert "Demon Voice" in names and len(names) == len(BUILTIN_EFFECT_PRESETS)
    demon = pm.get("effects", "Demon Voice")
    assert demon.category == "Horror" and demon.builtin
    data = normalize_data({"category": "Glitch", "chain": [{"effect": "bitcrusher", "params": {"bits": 99}},
                                                           {"effect": "nope"}]})
    assert len(data["chain"]) == 1 and data["chain"][0]["params"]["bits"] == 16
    pm.save(Preset("effects", "Mine", data))
    assert pm.get("effects", "Mine").category == "Glitch"
    demon.data["chain"] = demon.data["chain"][:1]
    pm.save(demon)
    assert pm.get("effects", "Demon Voice").modified
    pm.restore("effects", "Demon Voice")
    assert len(pm.get("effects", "Demon Voice").data["chain"]) == 4


def test_history_undo_redo_and_merge():
    h = History(merge_window=10)
    state = {"v": 0}
    h.record(dict(state), "a")
    state["v"] = 1
    h.record(dict(state), "drag", merge_key="slider")
    state["v"] = 2
    h.record(dict(state), "drag", merge_key="slider")
    state["v"] = 3
    back = h.undo(state)
    assert back == {"v": 1}
    back2 = h.undo(back)
    assert back2 == {"v": 0}
    assert h.redo(back2) == {"v": 1}
    h.record({"v": 9}, "new")
    assert not h.can_redo
