from __future__ import annotations

import math

NOTE_NAMES = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"]
TEMPERAMENTS = ("equal", "just", "pythagorean", "custom")

_JUST_5_LIMIT = [0.0, 11.73, 3.91, 15.64, -13.69, -1.96, -17.49, 1.96, 13.69, -15.64, 17.60, -11.73]
_PYTHAGOREAN = [0.0, -9.78, 3.91, -5.87, 7.82, -1.96, 11.73, 1.96, -7.82, 5.87, -3.91, 9.78]


def midi_of(pitch_class: int, octave: int) -> int:
    return (octave + 1) * 12 + pitch_class


def note_name(midi: int) -> str:
    return f"{NOTE_NAMES[midi % 12]}{midi // 12 - 1}"


def temperament_offset_cents(midi: int, temperament: str, root: int = 0,
                             custom: list[float] | None = None) -> float:
    interval = (midi - root) % 12
    if temperament == "just":
        return _JUST_5_LIMIT[interval]
    if temperament == "pythagorean":
        return _PYTHAGOREAN[interval]
    if temperament == "custom" and custom:
        return float(custom[midi % 12]) if len(custom) == 12 else 0.0
    return 0.0


def frequency_of(midi: int, a4_hz: float = 440.0, temperament: str = "equal",
                 root: int = 0, custom: list[float] | None = None) -> float:
    cents = (midi - 69) * 100.0 + temperament_offset_cents(midi, temperament, root, custom)
    return a4_hz * 2.0 ** (cents / 1200.0)


def hz_to_midi_float(hz: float, a4_hz: float = 440.0) -> float:
    return 69.0 + 12.0 * math.log2(hz / a4_hz)


def describe_hz(hz: float, a4_hz: float = 440.0) -> tuple[str, float]:
    m = hz_to_midi_float(hz, a4_hz)
    nearest = int(round(m))
    return note_name(nearest), (m - nearest) * 100.0


def cents_between(f_measured: float, f_target: float) -> float:
    return 1200.0 * math.log2(f_measured / f_target)
