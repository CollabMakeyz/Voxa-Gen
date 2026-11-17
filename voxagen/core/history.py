from __future__ import annotations

import copy
import time
from dataclasses import dataclass
from typing import Any


@dataclass
class _Entry:
    state: Any
    label: str
    merge_key: str
    stamp: float


class History:
    def __init__(self, limit: int = 200, merge_window: float = 1.2):
        self.limit = limit
        self.merge_window = merge_window
        self._undo: list[_Entry] = []
        self._redo: list[_Entry] = []

    def record(self, before: Any, label: str = "", merge_key: str = "") -> None:
        now = time.monotonic()
        if merge_key and self._undo:
            last = self._undo[-1]
            if last.merge_key == merge_key and now - last.stamp < self.merge_window:
                last.stamp = now
                self._redo.clear()
                return
        self._undo.append(_Entry(copy.deepcopy(before), label, merge_key, now))
        if len(self._undo) > self.limit:
            del self._undo[0]
        self._redo.clear()

    def break_merge(self) -> None:
        if self._undo:
            self._undo[-1].merge_key = ""

    def undo(self, current: Any) -> Any | None:
        if not self._undo:
            return None
        e = self._undo.pop()
        self._redo.append(_Entry(copy.deepcopy(current), e.label, "", time.monotonic()))
        return copy.deepcopy(e.state)

    def redo(self, current: Any) -> Any | None:
        if not self._redo:
            return None
        e = self._redo.pop()
        self._undo.append(_Entry(copy.deepcopy(current), e.label, "", time.monotonic()))
        return copy.deepcopy(e.state)

    def clear(self) -> None:
        self._undo.clear()
        self._redo.clear()

    @property
    def can_undo(self) -> bool:
        return bool(self._undo)

    @property
    def can_redo(self) -> bool:
        return bool(self._redo)

    @property
    def undo_label(self) -> str:
        return self._undo[-1].label if self._undo else ""

    @property
    def redo_label(self) -> str:
        return self._redo[-1].label if self._redo else ""
