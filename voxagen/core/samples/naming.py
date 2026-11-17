from __future__ import annotations

import re
from pathlib import Path

_TOKEN_RE = re.compile(r"(\d+)")
_VALID_ID_RE = re.compile(r"^[^\s<>:\"/\\|?*]+$")


def sample_id_from_path(path: str | Path) -> str:
    return Path(path).stem.strip().lower()


def normalize_token(token: str) -> str:
    t = token.strip().lower()
    if t.endswith(".wav"):
        t = t[:-4]
    return t


def is_valid_token(token: str) -> bool:
    return bool(token) and bool(_VALID_ID_RE.match(token))


def natural_key(name: str) -> tuple:
    parts = _TOKEN_RE.split(name.lower())
    key = []
    for p in parts:
        if not p:
            continue
        if p.isdigit():
            key.append((0, int(p), p))
        else:
            key.append((1, 0, p))
    return tuple(key)


def classify(sample_id: str) -> str:
    if sample_id.isdigit():
        return "numbered"
    m = re.match(r"^([a-z]+)(\d+)$", sample_id)
    if m:
        return "variation"
    if re.match(r"^[a-z]+$", sample_id):
        return "lettered"
    return "other"


def parse_sequence_text(text: str) -> list[str]:
    return [normalize_token(t) for t in re.split(r"[\s,;]+", text) if t.strip()]
