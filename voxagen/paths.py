from __future__ import annotations

import os
import sys
from pathlib import Path

from . import APP_ID


def resource_root() -> Path:
    base = getattr(sys, "_MEIPASS", None)
    if base:
        return Path(base)
    return Path(__file__).resolve().parent.parent


def assets_dir() -> Path:
    return resource_root() / "assets"


def user_data_dir() -> Path:
    override = os.environ.get("VOXAGEN_DATA_DIR")
    if override:
        p = Path(override)
    else:
        root = os.environ.get("APPDATA") or str(Path.home() / ".config")
        p = Path(root) / APP_ID
    p.mkdir(parents=True, exist_ok=True)
    return p


def presets_dir() -> Path:
    p = user_data_dir() / "presets"
    p.mkdir(parents=True, exist_ok=True)
    return p


def user_sounds_dir() -> Path:
    p = user_data_dir() / "sounds"
    p.mkdir(parents=True, exist_ok=True)
    return p


def cache_dir() -> Path:
    override = os.environ.get("VOXAGEN_CACHE_DIR")
    if override:
        p = Path(override)
    else:
        root = os.environ.get("LOCALAPPDATA") or str(user_data_dir())
        p = Path(root) / APP_ID / "cache"
    p.mkdir(parents=True, exist_ok=True)
    return p
