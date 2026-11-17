from __future__ import annotations

import hashlib
import json

import numpy as np

from ...models.config import EffectSlot, EffectsSettings
from .registry import EFFECTS, FxContext, get_effect

MAX_SLOTS = 12


def new_slot(effect_id: str) -> EffectSlot:
    e = get_effect(effect_id)
    if e is None:
        raise ValueError(f"Unknown effect: {effect_id}")
    return EffectSlot(effect_id, True, e.default_mix if e.has_mix else 1.0, e.defaults())


def validate_chain(chain: list[EffectSlot]) -> list[str]:
    problems = []
    if len(chain) > MAX_SLOTS:
        problems.append(f"The chain has {len(chain)} effects; the maximum is {MAX_SLOTS}.")
    for i, s in enumerate(chain):
        if s.effect not in EFFECTS:
            problems.append(f"Effect {i + 1} ('{s.effect}') is unknown and will be skipped.")
    return problems


def active_slots(fx: EffectsSettings) -> list[EffectSlot]:
    if not fx.enabled:
        return []
    return [s for s in fx.chain[:MAX_SLOTS] if s.enabled and s.effect in EFFECTS]


def chain_key(fx: EffectsSettings) -> str:
    slots = active_slots(fx)
    if not slots:
        return ""
    data = [(s.effect, round(float(s.mix), 6), get_effect(s.effect).resolve(s.params)) for s in slots]
    raw = json.dumps([data, fx.seed], sort_keys=True, default=str)
    return "fx:" + hashlib.blake2b(raw.encode(), digest_size=12).hexdigest()


def apply_slot(x: np.ndarray, sr: int, slot: EffectSlot, ctx: FxContext) -> np.ndarray:
    e = get_effect(slot.effect)
    if e is None or not slot.enabled:
        return x
    params = e.resolve(slot.params)
    y = np.asarray(e.process(x, sr, params, ctx), dtype=np.float64)
    if y.shape != x.shape:
        from .registry import _fit
        y = _fit(y.reshape(len(y), -1)[:, : x.shape[1]], len(x))
    y = np.nan_to_num(y, nan=0.0, posinf=0.0, neginf=0.0)
    if e.has_mix:
        m = float(np.clip(slot.mix, 0.0, 1.0))
        if m < 1.0:
            y = (1.0 - m) * x + m * y
    return y


def apply_chain(x: np.ndarray, sr: int, fx: EffectsSettings, target_hz: float = 0.0, note_index: int = 0,
                cancel=None) -> np.ndarray:
    slots = active_slots(fx)
    if not slots or len(x) == 0:
        return x
    ctx = FxContext(float(target_hz), int(fx.seed), int(note_index))
    y = np.asarray(x, dtype=np.float64)
    for s in slots:
        if cancel and cancel():
            from ..audio.pipeline import Cancelled
            raise Cancelled()
        y = apply_slot(y, sr, s, ctx)
    return y


def describe_chain(fx: EffectsSettings) -> str:
    names = [get_effect(s.effect).name for s in fx.chain if s.effect in EFFECTS and s.enabled]
    return " → ".join(names) if names else ""
