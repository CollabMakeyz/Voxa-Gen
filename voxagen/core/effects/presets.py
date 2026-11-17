from __future__ import annotations

from ...models.config import EffectSlot, EffectsSettings
from ...models.serialization import from_dict, to_dict
from .registry import EFFECTS, get_effect

CATEGORIES = ("Horror", "Normal FNF", "Robot", "Retro", "Monster", "Glitch", "Funny / Meme", "Experimental")


def _slot(effect: str, mix: float | None = None, **params) -> dict:
    e = get_effect(effect)
    values = e.defaults()
    values.update(params)
    return to_dict(EffectSlot(effect, True, e.default_mix if mix is None else mix, values))


BUILTIN_EFFECT_PRESETS: list[tuple[str, str, str, list[dict]]] = [
    ("Horror", "Demon Voice", "Deep monster layer, darker timbre and a little grit.", [
        _slot("formant_shift", shift_st=-4.0),
        _slot("double_pitch", interval_st=-12.0, detune_cents=10.0, level=0.7, formants="follow"),
        _slot("distortion", 0.25, drive_db=14.0, type="soft", tone_hz=3500.0, output_db=-4.0),
        _slot("eq", low_cut_hz=40.0, low_gain_db=3.0, high_gain_db=-4.0)]),
    ("Horror", "Whisper Ghost", "Breathy, wide and unsteady, like a voice from another room.", [
        _slot("eq", low_cut_hz=300.0, high_gain_db=3.0),
        _slot("pitch_variation", depth_cents=25.0, speed_hz=0.8),
        _slot("chorus", 0.6, voices=3, depth_ms=5.0, delay_ms=22.0),
        _slot("noise", type="pink", level_db=-20.0, follow=0.9)]),
    ("Normal FNF", "Clean Polish", "Removes rumble, adds presence and light warmth. Safe on any sample.", [
        _slot("eq", low_cut_hz=80.0, mid_freq_hz=3000.0, mid_gain_db=2.5, mid_q=0.9, high_gain_db=1.5),
        _slot("saturation", 1.0, drive_db=6.0, character="tape", warmth=0.3)]),
    ("Normal FNF", "Warm Studio", "Thicker and rounder, with a natural singer's vibrato.", [
        _slot("saturation", 1.0, drive_db=9.0, character="tube", warmth=0.5),
        _slot("vibrato", rate_hz=5.2, depth_cents=18.0, onset_ms=220.0),
        _slot("eq", low_cut_hz=70.0, low_gain_db=1.5, high_gain_db=-1.0)]),
    ("Robot", "Classic Robot", "Ring-modulated, note-locked robot that stays in tune across the chromatic.", [
        _slot("ring_modulator", 0.6, carrier="note", ratio=1.0, waveform="sine"),
        _slot("bitcrusher", 1.0, bits=10.0, rate_hz=22050.0),
        _slot("eq", low_cut_hz=120.0, mid_freq_hz=2000.0, mid_gain_db=3.0)]),
    ("Robot", "Metallic Android", "Inharmonic shimmer and a slow swirl.", [
        _slot("frequency_shifter", 0.7, shift_hz=80.0),
        _slot("phaser", 0.5, rate_hz=0.3, stages=8.0, feedback=0.6),
        _slot("ring_modulator", 0.3, carrier="note", ratio=2.0)]),
    ("Retro", "8-bit Console", "Crunchy old-console voice.", [
        _slot("bitcrusher", 1.0, bits=6.0, rate_hz=11025.0),
        _slot("eq", low_cut_hz=150.0, high_cut_hz=9000.0)]),
    ("Retro", "Old Radio", "Narrow band, warm valve and vinyl crackle.", [
        _slot("eq", low_cut_hz=400.0, mid_freq_hz=1800.0, mid_gain_db=4.0, high_cut_hz=3800.0),
        _slot("saturation", 1.0, drive_db=12.0, character="tube", warmth=0.6),
        _slot("noise", type="crackle", level_db=-26.0, follow=0.0)]),
    ("Monster", "Giant", "Huge throat and an octave-down layer.", [
        _slot("formant_shift", shift_st=-6.0),
        _slot("double_pitch", interval_st=-12.0, detune_cents=4.0, level=0.5, formants="keep"),
        _slot("saturation", 1.0, drive_db=8.0, character="tape", warmth=0.6)]),
    ("Monster", "Goblin", "Small, sharp and sneaky, with a fifth on top.", [
        _slot("formant_shift", shift_st=5.0),
        _slot("double_pitch", interval_st=7.0, detune_cents=12.0, level=0.35, formants="follow"),
        _slot("distortion", 0.2, drive_db=10.0, type="fuzz")]),
    ("Glitch", "Data Corruption", "Broken bits, a shifted spectrum and chopped volume.", [
        _slot("bitcrusher", 1.0, bits=4.0, rate_hz=8000.0),
        _slot("frequency_shifter", 0.4, shift_hz=-45.0),
        _slot("tremolo", rate_hz=11.0, depth=0.8, shape="square")]),
    ("Glitch", "Stutter", "Fast on/off chopping.", [
        _slot("tremolo", rate_hz=14.0, depth=1.0, shape="square"),
        _slot("bitcrusher", 0.5, bits=8.0, rate_hz=16000.0)]),
    ("Funny / Meme", "Chipmunk Choir", "Tiny voices singing in octaves.", [
        _slot("formant_shift", shift_st=7.0),
        _slot("double_pitch", interval_st=12.0, detune_cents=8.0, level=0.5, formants="follow"),
        _slot("chorus", 0.5, voices=4)]),
    ("Funny / Meme", "Underwater", "Bubbly, muffled and wobbly.", [
        _slot("eq", high_cut_hz=1600.0, low_gain_db=3.0),
        _slot("phaser", 0.7, rate_hz=1.2, depth=1.0, center_hz=600.0, feedback=0.7),
        _slot("vibrato", rate_hz=3.0, depth_cents=45.0, onset_ms=0.0)]),
    ("Experimental", "Alien Transmission", "Inharmonic carrier and swirling notches.", [
        _slot("ring_modulator", 0.5, carrier="note", ratio=2.5, waveform="triangle"),
        _slot("frequency_shifter", 0.5, shift_hz=-60.0),
        _slot("phaser", 0.5, rate_hz=2.0, stages=10.0)]),
    ("Experimental", "Dream Drift", "Slowly drifting, wide and soft.", [
        _slot("pitch_variation", depth_cents=15.0, speed_hz=0.5),
        _slot("chorus", 0.6, voices=3, rate_hz=0.3, depth_ms=6.0),
        _slot("eq", high_gain_db=-3.0, low_cut_hz=100.0)]),
]


def preset_data(fx: EffectsSettings, category: str) -> dict:
    return {"category": category if category in CATEGORIES else "Experimental",
            "chain": [to_dict(s) for s in fx.chain], "seed": int(fx.seed)}


def normalize_data(data: dict) -> dict:
    chain = []
    for raw in data.get("chain", []) or []:
        if not isinstance(raw, dict):
            continue
        slot = from_dict(EffectSlot, raw)
        e = get_effect(slot.effect)
        if e is None:
            continue
        slot.params = e.resolve(slot.params)
        slot.mix = float(min(1.0, max(0.0, slot.mix)))
        chain.append(to_dict(slot))
    cat = data.get("category", "Experimental")
    try:
        seed = int(data.get("seed", 7))
    except (TypeError, ValueError):
        seed = 7
    return {"category": cat if cat in CATEGORIES else "Experimental", "chain": chain, "seed": seed}


def chain_from_data(data: dict) -> list[EffectSlot]:
    return [from_dict(EffectSlot, s) for s in normalize_data(data)["chain"]]


assert all(s["effect"] in EFFECTS for _, _, _, slots in BUILTIN_EFFECT_PRESETS for s in slots)
