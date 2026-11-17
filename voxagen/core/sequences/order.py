from __future__ import annotations

import random
from dataclasses import dataclass, field

from ...models.config import OrderSettings
from ..samples.naming import natural_key, normalize_token, parse_sequence_text

BF_CLASSIC_NAME = "BF Classic Sequence"
BF_CLASSIC_TEXT = (
    "a e2 o e a2 o u i a o a2 e2 e u i a o i u a2 e2 u i u2 i u a a3 e2 e3 "
    "u a2 a e e2 u e2 e2 u a a2 e e2 u e2"
)
BF_CLASSIC_TOKENS: tuple[str, ...] = tuple(BF_CLASSIC_TEXT.split())


class OrderError(Exception):
    pass


@dataclass
class MissingSampleError(OrderError):
    missing: dict[str, list[int]] = field(default_factory=dict)

    def __str__(self) -> str:
        parts = [f"'{t}.wav' (position {', '.join(str(p + 1) for p in pos)})" for t, pos in self.missing.items()]
        return "Missing samples: " + "; ".join(parts)


@dataclass
class TokenStatus:
    position: int
    token: str
    resolved: str | None
    state: str


def validate_sequence(tokens: list[str], available: set[str], remap: dict[str, str] | None = None) -> list[TokenStatus]:
    remap = remap or {}
    out = []
    for i, raw in enumerate(tokens):
        t = normalize_token(raw)
        if not t:
            out.append(TokenStatus(i, raw, None, "invalid"))
        elif t in available:
            out.append(TokenStatus(i, t, t, "ok"))
        elif t in remap:
            target = remap[t]
            if target == "":
                out.append(TokenStatus(i, t, None, "skipped"))
            elif target in available:
                out.append(TokenStatus(i, t, target, "remapped"))
            else:
                out.append(TokenStatus(i, t, None, "missing"))
        else:
            out.append(TokenStatus(i, t, None, "missing"))
    return out


def resolve_sequence(tokens: list[str], available: set[str], remap: dict[str, str] | None = None) -> list[str]:
    statuses = validate_sequence(tokens, available, remap)
    missing: dict[str, list[int]] = {}
    for st in statuses:
        if st.state in ("missing", "invalid"):
            missing.setdefault(st.token or "<empty>", []).append(st.position)
    if missing:
        raise MissingSampleError(missing)
    resolved = [st.resolved for st in statuses if st.resolved is not None]
    if not resolved:
        raise OrderError("Every element of the sequence was skipped; nothing to play.")
    return resolved


def build_order(count: int, sample_ids: list[str], settings: OrderSettings) -> list[str]:
    if count <= 0:
        return []
    mode = settings.mode
    rng = random.Random(settings.seed)

    if mode == "vocal":
        seq = resolve_sequence(list(settings.sequence), set(sample_ids), settings.remap)
        return [seq[i % len(seq)] for i in range(count)]

    ids = sorted(sample_ids, key=natural_key)
    if not ids:
        raise OrderError("No usable samples are loaded.")

    if mode == "sequential":
        return [ids[i % len(ids)] for i in range(count)]

    if mode == "shuffle":
        out: list[str] = []
        while len(out) < count:
            cycle = ids[:]
            rng.shuffle(cycle)
            if out and len(cycle) > 1 and cycle[0] == out[-1]:
                j = rng.randrange(1, len(cycle))
                cycle[0], cycle[j] = cycle[j], cycle[0]
            out.extend(cycle)
        return out[:count]

    if mode == "random":
        return [rng.choice(ids) for _ in range(count)]

    raise OrderError(f"Unknown order mode: {mode}")


def sequence_from_text(text: str) -> list[str]:
    return parse_sequence_text(text)
