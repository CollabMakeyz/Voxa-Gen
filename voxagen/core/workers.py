from __future__ import annotations

import threading
import traceback
from typing import Any, Callable

from PySide6.QtCore import QObject, QThread, Signal

from .audio.pipeline import Cancelled


class _Worker(QObject):
    progress = Signal(str, int, int, str)
    succeeded = Signal(object)
    failed = Signal(object)
    cancelled = Signal()
    done = Signal()

    def __init__(self, fn: Callable[..., Any], cancel_event: threading.Event):
        super().__init__()
        self.fn = fn
        self.cancel_event = cancel_event

    def run(self) -> None:
        try:
            result = self.fn(self._progress, self.cancel_event.is_set)
            if self.cancel_event.is_set():
                self.cancelled.emit()
            else:
                self.succeeded.emit(result)
        except Cancelled:
            self.cancelled.emit()
        except Exception as exc:
            exc.traceback_text = traceback.format_exc()
            self.failed.emit(exc)
        finally:
            self.done.emit()

    def _progress(self, stage: str, cur: int, total: int, label: str) -> None:
        self.progress.emit(stage, cur, total, label)


class Task(QObject):
    progress = Signal(str, int, int, str)
    succeeded = Signal(object)
    failed = Signal(object)
    cancelled = Signal()
    finished = Signal()

    _alive: set["Task"] = set()

    def __init__(self, fn: Callable[..., Any], name: str = "task", parent=None):
        super().__init__(parent)
        self.name = name
        self._cancel = threading.Event()
        self._thread = QThread()
        self._worker = _Worker(fn, self._cancel)
        self._worker.moveToThread(self._thread)
        self._thread.started.connect(self._worker.run)
        self._worker.progress.connect(self.progress)
        self._worker.succeeded.connect(self.succeeded)
        self._worker.failed.connect(self.failed)
        self._worker.cancelled.connect(self.cancelled)
        self._worker.done.connect(self._thread.quit)
        self._thread.finished.connect(self._on_finished)
        self.running = False

    def start(self) -> "Task":
        Task._alive.add(self)
        self.running = True
        self._thread.start()
        return self

    def cancel(self) -> None:
        self._cancel.set()

    @property
    def is_cancelled(self) -> bool:
        return self._cancel.is_set()

    def wait(self, ms: int = 30000) -> bool:
        return self._thread.wait(ms)

    def _on_finished(self) -> None:
        self.running = False
        self.finished.emit()
        self._worker.deleteLater()
        self._thread.deleteLater()
        Task._alive.discard(self)

    @classmethod
    def cancel_all_and_wait(cls, ms: int = 5000) -> None:
        for t in list(cls._alive):
            t.cancel()
        for t in list(cls._alive):
            t._thread.wait(ms)
