from __future__ import annotations

from PySide6.QtCore import QRectF, Qt, Signal
from PySide6.QtGui import QPainter, QPen
from PySide6.QtWidgets import QSizePolicy, QWidget

from ...core.pitch.tuning import note_name
from .. import theme

BLACK = {1, 3, 6, 8, 10}


class ChromaticKeyboard(QWidget):
    noteClicked = Signal(int)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumHeight(74)
        self.setMaximumHeight(96)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.setMouseTracking(True)
        self.start_midi = 48
        self.count = 0
        self.states: list[str] = []
        self.tips: list[str] = []
        self.current = -1
        self._rects: list[tuple[QRectF, int, bool]] = []

    def set_range(self, start_midi: int, count: int) -> None:
        self.start_midi, self.count = start_midi, max(0, count)
        self.states = ["pending"] * self.count
        self.tips = [""] * self.count
        self.current = -1
        self._layout()
        self.update()

    def set_state(self, i: int, state: str, tip: str = "") -> None:
        if 0 <= i < self.count:
            self.states[i] = state
            if tip:
                self.tips[i] = tip
            self.update()

    def set_states(self, states: list[str], tips: list[str] | None = None) -> None:
        self.states = list(states)[: self.count] + ["pending"] * max(0, self.count - len(states))
        if tips is not None:
            self.tips = list(tips)[: self.count] + [""] * max(0, self.count - len(tips))
        self.update()

    def set_current(self, i: int) -> None:
        if i != self.current:
            self.current = i
            self.update()

    def resizeEvent(self, e):
        self._layout()
        super().resizeEvent(e)

    def _layout(self) -> None:
        self._rects = []
        if self.count == 0:
            return
        whites = [i for i in range(self.count) if (self.start_midi + i) % 12 not in BLACK]
        n_white = max(1, len(whites))
        ww = self.width() / n_white
        h = self.height()
        wi = 0
        white_x = {}
        for i in range(self.count):
            m = self.start_midi + i
            if m % 12 not in BLACK:
                r = QRectF(wi * ww, 0, ww, h)
                white_x[i] = wi * ww
                self._rects.append((r, i, False))
                wi += 1
        bw = ww * 0.6
        for i in range(self.count):
            m = self.start_midi + i
            if m % 12 in BLACK:
                left = white_x.get(i - 1, (white_x.get(i + 1, ww) - ww))
                r = QRectF(left + ww - bw / 2, 0, bw, h * 0.6)
                self._rects.append((r, i, True))

    def paintEvent(self, _):
        t = theme.current()
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        if self.count == 0:
            p.setPen(theme.qcolor(t.text_faint))
            p.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, "No notes")
            return
        f = p.font()
        f.setPointSizeF(theme.fs(7.0))
        p.setFont(f)
        for r, i, black in self._rects:
            state = self.states[i] if i < len(self.states) else "pending"
            base = theme.qcolor(t.key_black if black else t.key_white)
            if state == "missing":
                base = theme.qcolor(t.surface_alt)
            p.setPen(QPen(theme.qcolor(t.border_strong), 1))
            p.setBrush(base)
            p.drawRoundedRect(r.adjusted(0.5, 0, -0.5, -0.5), 2, 2)
            tone = {"ok": t.ok, "warn": t.warn, "error": t.error, "missing": t.text_faint}.get(state)
            if tone:
                strip = QRectF(r.x() + 2, r.bottom() - 5, r.width() - 4, 3)
                p.fillRect(strip, theme.qcolor(tone))
            if i == self.current:
                p.setBrush(theme.qcolor(t.accent, 200))
                p.setPen(Qt.PenStyle.NoPen)
                p.drawRoundedRect(r.adjusted(1.5, 1.5, -1.5, -7), 2, 2)
            if not black and r.width() > 16:
                m = self.start_midi + i
                p.setPen(theme.qcolor("#555" if t.name == "dark" else t.text_muted) if i != self.current
                         else theme.qcolor(t.accent_text))
                name = note_name(m) if m % 12 == 0 or r.width() > 30 else ""
                if name:
                    p.drawText(r.adjusted(0, 0, 0, -8), Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignBottom, name)

    def _index_at(self, pos) -> int:
        for r, i, black in reversed(self._rects):
            if r.contains(pos):
                return i
        return -1

    def mousePressEvent(self, e):
        i = self._index_at(e.position())
        if i >= 0:
            self.noteClicked.emit(i)

    def mouseMoveEvent(self, e):
        i = self._index_at(e.position())
        if i >= 0:
            from ...i18n import tr
            tip = tr("{note} · note {n}", note=note_name(self.start_midi + i), n=i + 1)
            if i < len(self.tips) and self.tips[i]:
                tip += f"\n{self.tips[i]}"
            self.setToolTip(tip)
