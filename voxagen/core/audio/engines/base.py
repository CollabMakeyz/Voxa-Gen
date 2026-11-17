from __future__ import annotations

import threading
from abc import ABC, abstractmethod
from collections import OrderedDict
from dataclasses import dataclass, field
from typing import Any

import numpy as np

from ....models.config import GeneratorConfig
from ....models.serialization import to_dict


@dataclass
class EngineOutput:
    audio: np.ndarray
    sr: int
    warnings: list[str] = field(default_factory=list)
    info: dict = field(default_factory=dict)


class Engine(ABC):
    id: str = "base"
    resampling_quality: str = "vhq"

    @abstractmethod
    def analysis_key(self) -> str:
        pass

    @abstractmethod
    def render_key(self) -> str:
        pass

    @abstractmethod
    def analyze(self, x: np.ndarray, sr: int) -> Any:
        ...

    @abstractmethod
    def render(self, analysis: Any, x: np.ndarray, sr: int, target_hz: float,
               duration_ratio: float = 1.0) -> EngineOutput:
        ...

    @property
    def keeps_channels(self) -> bool:
        return True


class AnalysisCache:

    def __init__(self, max_bytes: int = 768 * 1024 * 1024):
        self.max_bytes = max_bytes
        self._items: OrderedDict[tuple, tuple[Any, int]] = OrderedDict()
        self._size = 0
        self._lock = threading.Lock()
        self._key_locks: dict[tuple, threading.Lock] = {}

    @staticmethod
    def _sizeof(obj: Any) -> int:
        total = 0
        for v in getattr(obj, "__dict__", {}).values():
            if isinstance(v, np.ndarray):
                total += v.nbytes
            elif isinstance(v, (list, tuple)):
                total += sum(a.nbytes for a in v if isinstance(a, np.ndarray))
        return max(total, 1024)

    def get_or_create(self, key: tuple, factory):
        with self._lock:
            if key in self._items:
                self._items.move_to_end(key)
                return self._items[key][0]
            key_lock = self._key_locks.setdefault(key, threading.Lock())
        with key_lock:
            with self._lock:
                if key in self._items:
                    self._items.move_to_end(key)
                    return self._items[key][0]
            value = factory()
            self._store(key, value)
        with self._lock:
            self._key_locks.pop(key, None)
        return value

    def _store(self, key: tuple, value) -> None:
        size = self._sizeof(value)
        with self._lock:
            self._items[key] = (value, size)
            self._size += size
            while self._size > self.max_bytes and len(self._items) > 1:
                _, (_, s) = self._items.popitem(last=False)
                self._size -= s

    def clear(self) -> None:
        with self._lock:
            self._items.clear()
            self._size = 0


def params_key(obj) -> str:
    import json
    return json.dumps(to_dict(obj), sort_keys=True)


def get_engine(mode: str, config: GeneratorConfig) -> Engine:
    from .legacy import LegacyEngine
    from .natural import NaturalEngine
    from .robot import RobotEngine
    if mode == "natural":
        return NaturalEngine(config.natural, engine_id="natural")
    if mode == "lab":
        return NaturalEngine(config.lab, engine_id="lab")
    if mode == "robot":
        return RobotEngine(config.robot)
    if mode == "legacy":
        return LegacyEngine(config.legacy)
    raise ValueError(f"Unknown export mode: {mode}")
