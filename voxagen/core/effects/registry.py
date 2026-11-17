from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable

import numpy as np
from scipy import signal as sps

from ..audio.dsp import active_rms, db_to_gain


@dataclass(frozen=True)
class Param:
    key: str
    label: str
    lo: float = 0.0
    hi: float = 1.0
    default: float | str = 0.0
    unit: str = ""
    decimals: int = 2
    scale: float = 1.0
    choices: tuple[tuple[str, str], ...] = ()
    help: str = ""

    @property
    def is_choice(self) -> bool:
        return bool(self.choices)

    def clamp(self, v):
        if self.is_choice:
            keys = [k for k, _ in self.choices]
            return v if v in keys else self.default
        try:
            v = float(v)
        except (TypeError, ValueError):
            return self.default
        if not np.isfinite(v):
            return self.default
        return float(min(self.hi, max(self.lo, v)))


@dataclass
class FxContext:
    target_hz: float = 0.0
    seed: int = 0
    note_index: int = 0


@dataclass(frozen=True)
class Effect:
    id: str
    name: str
    summary: str
    help: str
    params: tuple[Param, ...]
    process: Callable
    has_mix: bool = True
    default_mix: float = 1.0
    cost: str = "light"
    tags: tuple[str, ...] = field(default_factory=tuple)

    def defaults(self) -> dict:
        return {p.key: p.default for p in self.params}

    def param(self, key: str) -> Param | None:
        return next((p for p in self.params if p.key == key), None)

    def resolve(self, values: dict | None) -> dict:
        values = values or {}
        return {p.key: p.clamp(values.get(p.key, p.default)) for p in self.params}


MIX_HELP = ("Blend between the untouched input (0 %) and the effect (100 %). Lower values keep more of the "
            "original voice.")


def _lfo(n: int, sr: int, rate: float, shape: str = "sine", phase: float = 0.0) -> np.ndarray:
    t = np.arange(n) / sr
    ph = 2 * np.pi * rate * t + phase
    if shape == "triangle":
        return 2.0 / np.pi * np.arcsin(np.sin(ph))
    if shape == "square":
        sq = np.tanh(8.0 * np.sin(ph))
        return sq / np.tanh(8.0)
    return np.sin(ph)


def _oversample(fn, x: np.ndarray, factor: int = 4) -> np.ndarray:
    if len(x) == 0:
        return x.copy()
    up = sps.resample_poly(x, factor, 1, axis=0)
    y = fn(up)
    out = sps.resample_poly(y, 1, factor, axis=0)
    return _fit(out, len(x))


def _fit(y: np.ndarray, n: int) -> np.ndarray:
    if len(y) >= n:
        return y[:n]
    pad = np.zeros((n - len(y),) + y.shape[1:])
    return np.concatenate([y, pad], axis=0)


def _dc_block(x: np.ndarray, sr: int) -> np.ndarray:
    sos = sps.butter(2, 15.0, "highpass", fs=sr, output="sos")
    return sps.sosfiltfilt(sos, x, axis=0) if len(x) > 30 else x


def _lowpass(x: np.ndarray, sr: int, hz: float, order: int = 2) -> np.ndarray:
    hz = min(hz, sr * 0.45)
    sos = sps.butter(order, hz, "lowpass", fs=sr, output="sos")
    return sps.sosfilt(sos, x, axis=0)


def _match_rms(y: np.ndarray, ref: np.ndarray, sr: int) -> np.ndarray:
    a, b = active_rms(ref, sr), active_rms(y, sr)
    if a > 0 and b > 0:
        return y * float(np.clip(a / b, 0.05, 20.0))
    return y


def _read_at(x: np.ndarray, pos: np.ndarray) -> np.ndarray:
    n = len(x)
    idx = np.arange(n)
    return np.stack([np.interp(pos, idx, x[:, c], left=0.0, right=0.0) for c in range(x.shape[1])], axis=1)


def _smooth_random(n: int, sr: int, rate: float, rng: np.random.Generator) -> np.ndarray:
    points = max(4, int(np.ceil(n / sr * rate)) + 4)
    knots = rng.uniform(-1.0, 1.0, points)
    xs = np.linspace(0, n - 1, points)
    from scipy.interpolate import PchipInterpolator
    curve = PchipInterpolator(xs, knots)(np.arange(n))
    curve -= curve.mean()
    m = np.max(np.abs(curve)) or 1.0
    return curve / m


def _rng(ctx: FxContext, salt: int) -> np.random.Generator:
    return np.random.default_rng([int(ctx.seed) & 0x7FFFFFFF, int(ctx.note_index), salt])


def _world(x1: np.ndarray, sr: int, frame_ms: float = 5.0):
    import pyworld as pw
    x1 = np.ascontiguousarray(x1, dtype=np.float64)
    f0, t = pw.dio(x1, sr, f0_floor=50.0, f0_ceil=1100.0, frame_period=frame_ms)
    f0 = pw.stonemask(x1, f0, t, sr)
    sp = pw.cheaptrick(x1, f0, t, sr)
    ap = pw.d4c(x1, f0, t, sr)
    return pw, f0, sp, ap


def _world_resynth(x: np.ndarray, sr: int, f0_ratio: float = 1.0, formant_alpha: float = 1.0) -> np.ndarray:
    from ..audio.engines.world_utils import warp_envelope
    out = np.zeros_like(x)
    for c in range(x.shape[1]):
        ch = x[:, c]
        if not np.any(np.abs(ch) > 1e-6):
            continue
        pw, f0, sp, ap = _world(ch, sr)
        sp2 = warp_envelope(sp, formant_alpha)
        f02 = f0 * f0_ratio
        nyq = sr / 2.0 - 50.0
        f02[f02 > nyq] = 0.0
        y = pw.synthesize(f02, np.ascontiguousarray(sp2), np.ascontiguousarray(ap), sr, 5.0)
        out[:, c] = _fit(y[:, None], len(ch))[:, 0]
    return out


def fx_distortion(x, sr, p, ctx):
    g = db_to_gain(p["drive_db"])
    kind = p["type"]

    def shape(u):
        u = u * g
        if kind == "hard":
            return np.clip(u, -1.0, 1.0)
        if kind == "fold":
            v = 0.25 * u + 0.25
            return 4.0 * np.abs(v - np.floor(v + 0.5)) - 1.0
        if kind == "fuzz":
            u = u + 0.3
            return np.sign(u) * (1.0 - np.exp(-np.abs(u)))
        return np.tanh(u)

    y = _oversample(shape, x, 4)
    y = _dc_block(y, sr)
    y = _lowpass(y, sr, p["tone_hz"])
    return y * db_to_gain(p["output_db"])


def fx_saturation(x, sr, p, ctx):
    g = db_to_gain(p["drive_db"])
    warmth = p["warmth"]
    tube = p["character"] == "tube"

    def shape(u):
        u = u * g
        if tube:
            b = warmth * 0.6
            y = np.tanh(u + b) - np.tanh(b)
            return np.where(y > 0, y, y * (1.0 - 0.35 * warmth))
        return np.tanh(u) + warmth * 0.15 * np.tanh(u) ** 2

    y = _oversample(shape, x, 2)
    y = _dc_block(y, sr)
    if not tube:
        y = _lowpass(y, sr, 18000.0 - 9000.0 * warmth, order=1)
    return _match_rms(y, x, sr)


def fx_formant_shift(x, sr, p, ctx):
    alpha = 2.0 ** (p["shift_st"] / 12.0)
    return _world_resynth(x, sr, 1.0, alpha)


def fx_tremolo(x, sr, p, ctx):
    n, ch = x.shape
    out = np.empty_like(x)
    for c in range(ch):
        phase = np.deg2rad(p["stereo_phase"]) * c
        lfo = _lfo(n, sr, p["rate_hz"], p["shape"], phase)
        gain = 1.0 - p["depth"] * (0.5 - 0.5 * lfo)
        out[:, c] = x[:, c] * gain
    return out


def fx_vibrato(x, sr, p, ctx):
    n = len(x)
    rate = max(0.05, p["rate_hz"])
    w = 2 * np.pi * rate
    amp = (2.0 ** (p["depth_cents"] / 1200.0) - 1.0) / w
    env = np.ones(n)
    onset = int(p["onset_ms"] / 1000.0 * sr)
    if onset > 0:
        env[:onset] = np.linspace(0.0, 1.0, min(onset, n))[: min(onset, n)]
    t = np.arange(n) / sr
    lfo = _lfo(n, sr, rate, p["shape"]) if p["shape"] != "sine" else np.sin(w * t)
    delay = amp * env * lfo * sr
    return _read_at(x, np.arange(n) - delay)


def fx_pitch_variation(x, sr, p, ctx):
    n = len(x)
    rng = _rng(ctx, 11)
    curve = _smooth_random(n, sr, p["speed_hz"], rng)
    cents = p["depth_cents"] * curve
    ratio = 2.0 ** (cents / 1200.0)
    pos = np.concatenate([[0.0], np.cumsum(ratio[:-1])])
    pos *= (n - 1) / max(pos[-1], 1.0)
    return _read_at(x, pos)


def fx_bitcrusher(x, sr, p, ctx):
    y = x
    hold = max(1.0, sr / max(100.0, p["rate_hz"]))
    if hold > 1.0001:
        idx = (np.floor(np.arange(len(x)) / hold) * hold).astype(int)
        y = y[np.clip(idx, 0, len(x) - 1)]
    levels = 2.0 ** (p["bits"] - 1)
    return np.round(y * levels) / levels


def fx_double_pitch(x, sr, p, ctx):
    ratio = 2.0 ** ((p["interval_st"] + p["detune_cents"] / 100.0) / 12.0)
    alpha = 1.0 if p["formants"] == "keep" else ratio
    copy = _world_resynth(x, sr, ratio, alpha)
    d = int(p["delay_ms"] / 1000.0 * sr)
    if d > 0:
        copy = np.concatenate([np.zeros((d, x.shape[1])), copy[:-d]], axis=0) if d < len(copy) else copy * 0
    return x + copy * p["level"]


def fx_frequency_shifter(x, sr, p, ctx):
    n = len(x)
    if n < 8:
        return x.copy()
    pad = 1 << int(np.ceil(np.log2(n + 1024)))
    t = np.arange(n) / sr
    rot = np.exp(2j * np.pi * p["shift_hz"] * t)
    out = np.empty_like(x)
    for c in range(x.shape[1]):
        a = sps.hilbert(x[:, c], N=pad)[:n]
        out[:, c] = np.real(a * rot)
    return out


def fx_chorus(x, sr, p, ctx):
    n, ch = x.shape
    voices = int(round(p["voices"]))
    base = p["delay_ms"] / 1000.0 * sr
    depth = p["depth_ms"] / 1000.0 * sr
    idx = np.arange(n)
    mono = x.mean(axis=1, keepdims=True) if ch > 1 else x
    acc = np.zeros((n, ch))
    for v in range(voices):
        rate = p["rate_hz"] * (1.0 + 0.17 * v)
        phase = 2 * np.pi * v / max(1, voices)
        delay = base + depth * 0.5 * (1.0 + np.sin(2 * np.pi * rate * idx / sr + phase))
        wet = _read_at(mono, idx - delay)[:, 0]
        if ch == 1:
            acc[:, 0] += wet
        else:
            pan = (v / max(1, voices - 1) - 0.5) * p["spread"] if voices > 1 else 0.0
            acc[:, 0] += wet * np.sqrt(0.5 - pan)
            acc[:, 1] += wet * np.sqrt(0.5 + pan)
    return acc / np.sqrt(voices)


def fx_phaser(x, sr, p, ctx):
    n, ch = x.shape
    stages = int(round(p["stages"] / 2.0) * 2) or 2
    block = 64
    blocks = int(np.ceil(n / block))
    tb = (np.arange(blocks) * block + block / 2) / sr
    lfo = np.sin(2 * np.pi * p["rate_hz"] * tb)
    fc = np.clip(p["center_hz"] * 2.0 ** (2.0 * p["depth"] * lfo), 30.0, sr * 0.45)
    fb = p["feedback"]
    from math import comb
    k = np.tan(np.pi * fc / sr)
    a = (k - 1.0) / (k + 1.0)
    binom = np.array([comb(stages, i) for i in range(stages + 1)], dtype=float)
    pw = np.arange(stages + 1)
    num = binom[None, :] * a[:, None] ** (stages - pw)[None, :]
    den = binom[None, :] * a[:, None] ** pw[None, :]
    den = den - fb * num
    out = np.empty_like(x)
    for c in range(ch):
        zi = np.zeros(stages)
        y = np.empty(n)
        for b in range(blocks):
            seg = x[b * block:(b + 1) * block, c]
            y[b * block:b * block + len(seg)], zi = sps.lfilter(num[b], den[b], seg, zi=zi)
        out[:, c] = y
    return out * (1.0 - 0.5 * fb)


def fx_ring_modulator(x, sr, p, ctx):
    n = len(x)
    hz = p["freq_hz"]
    if p["carrier"] == "note" and ctx.target_hz > 0:
        hz = ctx.target_hz * p["ratio"]
    hz = min(hz, sr * 0.45)
    car = _lfo(n, sr, hz, p["waveform"])
    return x * car[:, None]


def fx_noise(x, sr, p, ctx):
    n, ch = x.shape
    rng = _rng(ctx, 23)
    kind = p["type"]
    white = rng.standard_normal((n, ch))
    if kind == "pink":
        b = [0.049922035, -0.095993537, 0.050612699, -0.004408786]
        a = [1, -2.494956002, 2.017265875, -0.522189400]
        noise = sps.lfilter(b, a, white, axis=0)
    elif kind == "brown":
        noise = sps.lfilter([1.0], [1.0, -0.995], white, axis=0)
        noise = _dc_block(noise, sr)
    elif kind == "crackle":
        hits = (rng.random((n, ch)) < 6.0 / sr).astype(float) * rng.uniform(0.3, 1.0, (n, ch))
        noise = sps.lfilter([1.0], [1.0, -0.6], hits, axis=0)
        hiss = _lowpass(white * 0.05, sr, 6000.0)
        noise = noise + hiss
    else:
        noise = white
    noise /= (np.sqrt(np.mean(noise ** 2)) + 1e-12)
    ref = active_rms(x, sr) or 0.1
    noise *= ref * db_to_gain(p["level_db"])
    if p["follow"] > 0:
        env = np.sqrt(sps.lfilter([0.002], [1.0, -0.998], np.mean(x ** 2, axis=1)).clip(0))
        env /= (env.max() + 1e-12)
        noise *= (1.0 - p["follow"] + p["follow"] * env)[:, None]
    return x + noise


def _rbj(kind: str, f0: float, sr: int, gain_db: float = 0.0, q: float = 0.707) -> np.ndarray:
    a_ = 10 ** (gain_db / 40.0)
    w = 2 * np.pi * min(f0, sr * 0.45) / sr
    cw, sw = np.cos(w), np.sin(w)
    alpha = sw / (2 * q)
    if kind == "peak":
        b = [1 + alpha * a_, -2 * cw, 1 - alpha * a_]
        a = [1 + alpha / a_, -2 * cw, 1 - alpha / a_]
    elif kind == "lowshelf":
        s = 2 * np.sqrt(a_) * alpha
        b = [a_ * ((a_ + 1) - (a_ - 1) * cw + s), 2 * a_ * ((a_ - 1) - (a_ + 1) * cw), a_ * ((a_ + 1) - (a_ - 1) * cw - s)]
        a = [(a_ + 1) + (a_ - 1) * cw + s, -2 * ((a_ - 1) + (a_ + 1) * cw), (a_ + 1) + (a_ - 1) * cw - s]
    else:
        s = 2 * np.sqrt(a_) * alpha
        b = [a_ * ((a_ + 1) + (a_ - 1) * cw + s), -2 * a_ * ((a_ - 1) + (a_ + 1) * cw), a_ * ((a_ + 1) + (a_ - 1) * cw - s)]
        a = [(a_ + 1) - (a_ - 1) * cw + s, 2 * ((a_ - 1) - (a_ + 1) * cw), (a_ + 1) - (a_ - 1) * cw - s]
    b, a = np.array(b) / a[0], np.array(a) / a[0]
    return np.concatenate([b, a])[None, :]


def fx_eq(x, sr, p, ctx):
    sos = []
    if p["low_cut_hz"] > 20.5:
        sos.append(sps.butter(2, min(p["low_cut_hz"], sr * 0.45), "highpass", fs=sr, output="sos"))
    if abs(p["low_gain_db"]) > 0.01:
        sos.append(_rbj("lowshelf", p["low_freq_hz"], sr, p["low_gain_db"]))
    if abs(p["mid_gain_db"]) > 0.01:
        sos.append(_rbj("peak", p["mid_freq_hz"], sr, p["mid_gain_db"], p["mid_q"]))
    if abs(p["high_gain_db"]) > 0.01:
        sos.append(_rbj("highshelf", p["high_freq_hz"], sr, p["high_gain_db"]))
    if p["high_cut_hz"] < min(19999.0, sr * 0.45):
        sos.append(sps.butter(2, p["high_cut_hz"], "lowpass", fs=sr, output="sos"))
    if not sos:
        return x.copy()
    return sps.sosfilt(np.concatenate(sos, axis=0), x, axis=0)


SHAPES = (("sine", "Sine"), ("triangle", "Triangle"), ("square", "Square"))

EFFECTS: dict[str, Effect] = {}


def _add(e: Effect) -> None:
    EFFECTS[e.id] = e


_add(Effect(
    "distortion", "Distortion", "Hard, gritty clipping for aggressive or broken voices.",
    'Distortion drives the voice into a clipper. New harmonics pile up, and loud parts get dirtier than quiet ones: angry, broken, a blown-out speaker. Villains and screams live here. Drive is how hard it hits, Type the kind of clipping, Tone takes the edge off the top. Start at 12-18 dB of drive with 30-50 % mix.',
    (Param("drive_db", "Drive", 0, 48, 18.0, " dB", 1, help="How hard the voice hits the clipper. More drive = more grit and sustain."),
     Param("type", "Type", default="soft", choices=(("soft", "Soft (warm)"), ("hard", "Hard (harsh)"),
                                                    ("fold", "Wavefold (metallic)"), ("fuzz", "Fuzz (buzzy)")),
           help="Soft rounds the peaks, Hard cuts them flat, Wavefold folds them back (metallic), Fuzz is asymmetric and buzzy."),
     Param("tone_hz", "Tone", 500, 16000, 6000.0, " Hz", 0, help="Low-pass after the clipper. Lower values remove fizz and make the sound darker."),
     Param("output_db", "Output", -24, 6, -6.0, " dB", 1, help="Level after the effect, to keep loudness under control.")),
    fx_distortion, default_mix=0.4, tags=("Horror", "Monster", "Glitch")))

_add(Effect(
    "saturation", "Saturation", "Gentle tape or tube warmth; thicker without sounding broken.",
    "Saturation rounds off the peaks and adds a few low harmonics. Fuller, warmer, still clean. That's what sets it apart from Distortion. The level is matched to the input, so it won't just get louder. Good for a thin sample or an old-record feel. Character picks tape (smooth top) or tube (even harmonics); Warmth adds asymmetry. 6-10 dB of drive stays subtle.",
    (Param("drive_db", "Drive", 0, 24, 9.0, " dB", 1, help="How much the voice is pushed into the soft curve."),
     Param("character", "Character", default="tape", choices=(("tape", "Tape"), ("tube", "Tube")),
           help="Tape is smooth and slightly darker; Tube adds even harmonics for a richer sound."),
     Param("warmth", "Warmth", 0, 1, 0.4, " %", 0, 100, help="Asymmetry and darkening. Higher = warmer and rounder.")),
    fx_saturation, default_mix=1.0, tags=("Normal FNF", "Retro")))

_add(Effect(
    "formant_shift", "Formant Shift", "Changes the voice's timbre (size of the throat) without changing the note.",
    "Formant Shift moves the resonances of the vocal tract and leaves the note alone. Positive values sound smaller and younger (cartoon, chipmunk); negative ones bigger and deeper (giant, monster). The chromatic stays in tune. It runs a voice analysis, so it's slower than the other effects. ±2-4 semitones still sounds natural.",
    (Param("shift_st", "Shift", -12, 12, 3.0, " st", 1,
           help="Resonance shift in semitones. + = smaller/brighter voice, - = bigger/darker voice. 0 = no change."),),
    fx_formant_shift, default_mix=1.0, cost="heavy", tags=("Monster", "Funny / Meme", "Horror")))

_add(Effect(
    "tremolo", "Tremolo", "Pulses the VOLUME up and down at a steady speed.",
    'Tremolo moves the volume up and down; the pitch stays put. The voice pulses, stutters or wobbles. Shaky, nervous, retro, or square waves for a chopped glitch. Rate is pulses per second, Depth how deep the dips go, Shape the curve of each pulse. 5-7 Hz at 50 % depth is the classic wobble.',
    (Param("rate_hz", "Rate", 0.5, 20, 6.0, " Hz", 2, help="Pulses per second."),
     Param("depth", "Depth", 0, 1, 0.6, " %", 0, 100, help="How quiet the dips get. 100 % = down to silence."),
     Param("shape", "Shape", default="sine", choices=SHAPES, help="Sine is smooth, Triangle is linear, Square chops on/off."),
     Param("stereo_phase", "Stereo phase", 0, 180, 0.0, "°", 0,
           help='Offsets the right channel in stereo exports. The pulse then moves left and right. No effect in mono.')),
    fx_tremolo, has_mix=False, tags=("Retro", "Glitch")))

_add(Effect(
    "vibrato", "Vibrato", "Wobbles the PITCH up and down around the note at a steady speed.",
    'Vibrato raises and lowers the pitch at a steady speed, the way a singer does. The average stays on the note. Expressive held notes, old cartoons, or seasick at high depth. Rate is wobbles per second, Depth how far the pitch moves in cents (100 cents = 1 semitone), Onset how long it waits to fade in. 5-6 Hz and 20-40 cents sounds natural.',
    (Param("rate_hz", "Rate", 0.5, 12, 5.5, " Hz", 2, help="Wobbles per second."),
     Param("depth_cents", "Depth", 0, 200, 35.0, " ct", 0, help="Maximum pitch deviation in cents (100 = one semitone)."),
     Param("onset_ms", "Onset", 0, 1000, 150.0, " ms", 0, help='Fade-in time. The attack of the note stays steady.'),
     Param("shape", "Shape", default="sine", choices=SHAPES[:2], help="Sine is smooth; Triangle sweeps at constant speed.")),
    fx_vibrato, has_mix=False, tags=("Normal FNF", "Funny / Meme")))

_add(Effect(
    "pitch_variation", "Pitch Variation", "Random, slow pitch drift around the note (unsteady, alive).",
    "Pitch Variation lets the pitch wander around the note, randomly but smoothly, with the average still in tune. There's no steady rhythm like Vibrato has, so it comes out unsteady, drunk, ghostly, or just more human. The randomness is fixed per note: preview and export match. Depth is the largest deviation in cents, Speed how often it turns. Under 20 cents stays subtle.",
    (Param("depth_cents", "Depth", 0, 100, 18.0, " ct", 0, help="Largest deviation from the note, in cents."),
     Param("speed_hz", "Speed", 0.1, 8, 1.5, " Hz", 2, help="How often the drift changes direction per second.")),
    fx_pitch_variation, has_mix=False, tags=("Horror", "Experimental")))

_add(Effect(
    "bitcrusher", "BitCrusher", "Lo-fi digital grit: fewer bits and a lower sample rate.",
    'BitCrusher lowers the bit depth and the sample rate of the voice. Fewer bits bring hiss and harsh steps; a lower rate brings metallic aliasing. 8-bit, old consoles, broken radio. 8 bits at about 11 kHz is the classic console; 4 bits is wrecked.',
    (Param("bits", "Bits", 1, 16, 8.0, " bit", 0, help="Resolution. 16 = clean, 8 = retro, 1-4 = destroyed."),
     Param("rate_hz", "Sample rate", 1000, 48000, 11025.0, " Hz", 0,
           help="Rate the voice is held at. Lower = more metallic aliasing.")),
    fx_bitcrusher, default_mix=1.0, tags=("Retro", "Glitch", "Robot")))

_add(Effect(
    "double_pitch", "Double Pitch", "Adds a transposed copy of the voice (octave, fifth…) on top.",
    "Double Pitch adds a second voice a musical interval away, like singing in octaves or harmony. The original stays as it is; the copy comes in at the level you set. -12 gives a monster layer, +12 a cartoon one, +7 a power-chord feel. Detune makes the two voices beat against each other. Formants decides whether the copy keeps the original timbre or follows the pitch. It uses voice analysis, so it's slower.",
    (Param("interval_st", "Interval", -24, 24, -12.0, " st", 0, help="Transposition of the copy in semitones (12 = one octave)."),
     Param("detune_cents", "Detune", -50, 50, 6.0, " ct", 0, help="Small offset that makes the layer beat and sound thicker."),
     Param("level", "Level", 0, 1.5, 0.6, " %", 0, 100, help="Volume of the copy relative to the original."),
     Param("formants", "Formants", default="keep", choices=(("keep", "Keep voice timbre"), ("follow", "Follow the pitch")),
           help="Keep = natural layer; Follow = chipmunk/giant timbre on the copy."),
     Param("delay_ms", "Delay", 0, 60, 0.0, " ms", 0, help="Starts the copy slightly later for a doubled feel.")),
    fx_double_pitch, has_mix=False, cost="heavy", tags=("Monster", "Funny / Meme", "Horror")))

_add(Effect(
    "frequency_shifter", "Frequency Shifter", "Moves every frequency by the same number of Hz (metallic, inharmonic).",
    'The Frequency Shifter adds the same number of hertz to every part of the sound. A pitch shift keeps the harmonics in proportion; this breaks them. The voice goes metallic, alien or bell-like, and a little out of tune. 5-30 Hz gives a phasing shimmer; 100 Hz and up sounds robotic. Positive goes up, negative goes down.',
    (Param("shift_hz", "Shift", -1000, 1000, 120.0, " Hz", 1, help="Hertz added to every component of the sound."),),
    fx_frequency_shifter, default_mix=1.0, tags=("Robot", "Experimental")))

_add(Effect(
    "chorus", "Chorus", "Several slightly detuned, delayed copies: a wider, ensemble voice.",
    'Chorus mixes in copies of the voice on short, slowly moving delays. Tiny pitch and timing differences make it sound like several singers, wider and softer. Dreamy, choir-like, or a ghost. Voices is how many copies, Rate and Depth how much they move, Delay how far behind they sit, Spread how wide they go in stereo.',
    (Param("voices", "Voices", 1, 4, 2.0, "", 0, help="Number of copies."),
     Param("rate_hz", "Rate", 0.05, 5, 0.8, " Hz", 2, help="How fast the copies drift."),
     Param("depth_ms", "Depth", 0, 10, 3.0, " ms", 1, help="How much the copies drift (more = more detune)."),
     Param("delay_ms", "Delay", 5, 40, 15.0, " ms", 1, help="Base delay of the copies."),
     Param("spread", "Spread", 0, 1, 0.7, " %", 0, 100, help="Stereo width of the copies (stereo exports only).")),
    fx_chorus, default_mix=0.5, tags=("Horror", "Funny / Meme", "Experimental")))

_add(Effect(
    "phaser", "Phaser", "Sweeping notches that make the voice swirl like a jet.",
    'The Phaser mixes the voice with a phase-shifted copy, which cuts moving notches into the spectrum. It swooshes and swirls: underwater, spacey, psychedelic. Rate is the sweep speed, Depth how far it sweeps, Center where the notches sit, Stages how many there are, Feedback how sharply they ring.',
    (Param("rate_hz", "Rate", 0.05, 5, 0.5, " Hz", 2, help="Sweeps per second."),
     Param("depth", "Depth", 0, 1, 0.8, " %", 0, 100, help="Sweep range (up to ±2 octaves)."),
     Param("center_hz", "Center", 200, 4000, 900.0, " Hz", 0, help="Middle of the sweep."),
     Param("stages", "Stages", 2, 12, 6.0, "", 0, help="More stages = more notches and a stronger effect."),
     Param("feedback", "Feedback", 0, 0.9, 0.5, " %", 0, 100, help="Resonance of the notches.")),
    fx_phaser, default_mix=0.5, tags=("Experimental", "Funny / Meme")))

_add(Effect(
    "ring_modulator", "Ring Modulator", "Multiplies the voice by a tone: robotic, bell-like, Dalek voices.",
    "The Ring Modulator multiplies the voice by a second tone, the carrier. The rhythm of the words survives, but the pitch turns into metallic sum and difference tones. That's the old robot voice. With the carrier following the note, the robot sounds the same across the whole chromatic; a fixed carrier gives each note its own colour. 30-60 % mix keeps the words understandable.",
    (Param("carrier", "Carrier", default="note", choices=(("note", "Follows the note"), ("fixed", "Fixed frequency")),
           help="Follows the note: carrier = note × ratio. Fixed: the same frequency for every note."),
     Param("ratio", "Ratio", 0.25, 8, 1.5, "×", 2, help="Carrier frequency as a multiple of the note (when following the note)."),
     Param("freq_hz", "Frequency", 20, 4000, 440.0, " Hz", 0, help="Carrier frequency (when fixed)."),
     Param("waveform", "Waveform", default="sine", choices=SHAPES, help="Sine is smooth; Square and Triangle add buzz.")),
    fx_ring_modulator, default_mix=0.5, tags=("Robot", "Experimental")))

_add(Effect(
    "noise", "Noise", "Adds hiss, rumble or vinyl crackle under the voice.",
    'Noise puts a noise layer under the voice. Its level is relative to the voice: quiet and loud samples get the same amount. Follow makes it rise and fall with the voice, and the gaps between notes stay clean. Radio, old tape, whispers, breathy horror. Types: white (bright hiss), pink (soft hiss), brown (rumble), crackle (vinyl).',
    (Param("type", "Type", default="pink", choices=(("white", "White hiss"), ("pink", "Pink hiss"),
                                                    ("brown", "Brown rumble"), ("crackle", "Vinyl crackle")),
           help="Colour of the noise."),
     Param("level_db", "Level", -60, 0, -24.0, " dB", 1, help="Noise level relative to the voice. -24 dB is clearly audible but behind it."),
     Param("follow", "Follow voice", 0, 1, 0.8, " %", 0, 100, help="100 % = noise only while the voice sounds; 0 % = constant.")),
    fx_noise, has_mix=False, tags=("Retro", "Horror")))

_add(Effect(
    "eq", "EQ", "Shapes the tone: cut rumble, add presence, make it darker or brighter.",
    'The EQ boosts or cuts frequency ranges. Low cut clears rumble and mic noise. The low shelf adds or takes away body, the mid band handles presence and nasal tone, the high shelf adds air or darkness, and high cut removes hiss or fakes a phone or radio. Moves of 2-4 dB are usually plenty. Everything at 0 dB with the cuts at their limits changes nothing.',
    (Param("low_cut_hz", "Low cut", 20, 1000, 60.0, " Hz", 0, help="Removes everything below. 20 Hz = off."),
     Param("low_freq_hz", "Low shelf freq.", 40, 1000, 200.0, " Hz", 0, help="Where the low shelf starts."),
     Param("low_gain_db", "Low shelf", -18, 18, 0.0, " dB", 1, help="Body and weight of the voice."),
     Param("mid_freq_hz", "Mid freq.", 200, 8000, 1500.0, " Hz", 0, help="Centre of the mid band."),
     Param("mid_gain_db", "Mid", -18, 18, 0.0, " dB", 1, help="Presence (2-4 kHz) or nasal tone (800 Hz-1.5 kHz)."),
     Param("mid_q", "Mid width (Q)", 0.3, 8, 1.0, "", 2, help="Higher Q = narrower band."),
     Param("high_freq_hz", "High shelf freq.", 1500, 16000, 6000.0, " Hz", 0, help="Where the high shelf starts."),
     Param("high_gain_db", "High shelf", -18, 18, 0.0, " dB", 1, help="Air and brightness."),
     Param("high_cut_hz", "High cut", 2000, 20000, 20000.0, " Hz", 0, help="Removes everything above. 20000 Hz = off.")),
    fx_eq, has_mix=False, tags=("Normal FNF", "Retro")))


EFFECT_ORDER = ("eq", "saturation", "distortion", "formant_shift", "double_pitch", "vibrato", "pitch_variation",
                "tremolo", "chorus", "phaser", "frequency_shifter", "ring_modulator", "bitcrusher", "noise")


def get_effect(effect_id: str) -> Effect | None:
    return EFFECTS.get(effect_id)
