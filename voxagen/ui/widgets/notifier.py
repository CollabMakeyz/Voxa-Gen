from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable

from PySide6.QtCore import (
    QEasingCurve, QElapsedTimer, QParallelAnimationGroup, QPoint, QPropertyAnimation, QRectF, Qt, QTimer,
    Signal,
)
from PySide6.QtGui import QColor, QGuiApplication, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QWidget

from .. import icons, theme

WIDTH = 412
MARGIN = 16
GAP = 10
MAX_VISIBLE = 4
RADIUS = theme.RADIUS_CONTROL

TITLES = {"ok": "Done", "warn": "Attention", "error": "Error", "info": "Voxa GEN"}
ICONS = {"ok": "check", "warn": "warning", "error": "error", "info": "info"}


@dataclass
class Action:
    label: str
    callback: Callable[[], None]
    primary: bool = False


@dataclass
class NotificationSpec:
    title: str
    message: str
    tone: str = "info"
    actions: list[Action] = field(default_factory=list)
    ms: int | None = None


class Notification(QWidget):
    closed = Signal(object)

    def __init__(self, spec: NotificationSpec):
        super().__init__(None, Qt.WindowType.Tool | Qt.WindowType.FramelessWindowHint
                         | Qt.WindowType.WindowStaysOnTopHint | Qt.WindowType.WindowDoesNotAcceptFocus)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
        self.setObjectName("DesktopNotification")
        self.spec = spec
        self.duration = spec.ms or (9000 if spec.tone in ("error", "warn") or spec.actions else 4500)
        self._elapsed = QElapsedTimer()
        self._remaining = self.duration
        self._closing = False
        self.setFixedWidth(WIDTH)

        tone_color = self._tone_color()
        root = QHBoxLayout(self)
        root.setContentsMargins(16, 16, 8, 16)
        root.setSpacing(12)
        ic = QLabel()
        ic.setFixedSize(20, 20)
        ic.setPixmap(icons.icon(ICONS.get(spec.tone, "info"), color=tone_color.name(), size=20).pixmap(20, 20))
        ic.setContentsMargins(0, 2, 0, 0)
        icol = QVBoxLayout()
        icol.setContentsMargins(0, 3, 0, 0)
        icol.addWidget(ic)
        icol.addStretch(1)
        root.addLayout(icol)

        col = QVBoxLayout()
        col.setSpacing(4)
        title = QLabel(spec.title)
        title.setObjectName("NotifyTitle")
        title.setWordWrap(True)
        col.addWidget(title)
        if spec.message:
            msg = QLabel(spec.message.replace("\\", "\\\u200b").replace("/", "/\u200b"))
            msg.setObjectName("NotifyBody")
            msg.setWordWrap(True)
            msg.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
            col.addWidget(msg)
        if spec.actions:
            row = QHBoxLayout()
            row.setSpacing(8)
            row.setContentsMargins(0, 12, 0, 0)
            for a in spec.actions:
                b = QPushButton(a.label)
                b.setObjectName("NotifyButton")
                b.setCursor(Qt.CursorShape.PointingHandCursor)
                b.setFocusPolicy(Qt.FocusPolicy.NoFocus)
                b.clicked.connect(lambda _=False, cb=a.callback: self._run(cb))
                row.addWidget(b)
            row.addStretch(1)
            col.addLayout(row)
        root.addLayout(col, 1)

        close = QPushButton()
        close.setObjectName("NotifyClose")
        close.setIcon(icons.icon("close", size=14))
        close.setFixedSize(32, 32)
        close.setCursor(Qt.CursorShape.PointingHandCursor)
        close.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        close.setToolTip("Dismiss")
        close.clicked.connect(self.dismiss)
        root.addWidget(close, 0, Qt.AlignmentFlag.AlignTop)

        self._tick = QTimer(self)
        self._tick.setInterval(40)
        self._tick.timeout.connect(self._on_tick)
        self.adjustSize()

    def start(self) -> None:
        self._elapsed.start()
        self._tick.start()

    def _left(self) -> int:
        return max(0, self._remaining - (self._elapsed.elapsed() if self._tick.isActive() else 0))

    def _on_tick(self) -> None:
        if self._left() <= 0:
            self.dismiss()
        self.update()

    def enterEvent(self, e):
        if self._tick.isActive():
            self._remaining = self._left()
            self._tick.stop()
            self.update()
        super().enterEvent(e)

    def leaveEvent(self, e):
        if not self._closing:
            self.start()
        super().leaveEvent(e)

    def _run(self, cb) -> None:
        try:
            cb()
        finally:
            self.dismiss()

    def dismiss(self) -> None:
        if self._closing:
            return
        self._closing = True
        self._tick.stop()
        anim = QPropertyAnimation(self, b"windowOpacity", self)
        anim.setDuration(160)
        anim.setStartValue(self.windowOpacity())
        anim.setEndValue(0.0)
        anim.finished.connect(self._finish)
        anim.start()

    def _finish(self) -> None:
        self.closed.emit(self)
        self.close()

    def _tone_color(self) -> QColor:
        t = theme.current()
        return QColor({"ok": t.ok, "warn": t.warn, "error": t.error}.get(self.spec.tone, t.accent))

    def paintEvent(self, _):
        t = theme.current()
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        r = QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5)
        path = QPainterPath()
        path.addRoundedRect(r, RADIUS, RADIUS)
        p.fillPath(path, QColor(t.bg))
        p.setPen(QPen(QColor(t.text_faint), 1))
        p.drawPath(path)


class Notifier:

    def __init__(self, anchor: QWidget | None = None):
        self.anchor = anchor
        self.items: list[Notification] = []

    def _area(self):
        screen = (self.anchor.screen() if self.anchor is not None else None) or QGuiApplication.primaryScreen()
        return screen.availableGeometry()

    def notify(self, spec: NotificationSpec) -> Notification:
        n = Notification(spec)
        n.closed.connect(self._removed)
        self.items.insert(0, n)
        while len(self.items) > MAX_VISIBLE:
            self.items[-1].dismiss()
            self.items.pop()
        area = self._area()
        target = QPoint(area.right() - WIDTH - MARGIN + 1, area.top() + MARGIN)
        n.move(target + QPoint(40, 0))
        n.setWindowOpacity(0.0)
        n.show()
        group = QParallelAnimationGroup(n)
        slide = QPropertyAnimation(n, b"pos")
        slide.setDuration(220)
        slide.setStartValue(target + QPoint(40, 0))
        slide.setEndValue(target)
        slide.setEasingCurve(QEasingCurve.Type.OutCubic)
        fade = QPropertyAnimation(n, b"windowOpacity")
        fade.setDuration(180)
        fade.setStartValue(0.0)
        fade.setEndValue(1.0)
        group.addAnimation(slide)
        group.addAnimation(fade)
        group.start()
        n._enter = group
        n.start()
        self._relayout(skip=n)
        return n

    def _removed(self, n: Notification) -> None:
        if n in self.items:
            self.items.remove(n)
        self._relayout()

    def _relayout(self, skip: Notification | None = None) -> None:
        area = self._area()
        y = area.top() + MARGIN
        x = area.right() - WIDTH - MARGIN + 1
        for n in self.items:
            if n is not skip:
                anim = QPropertyAnimation(n, b"pos", n)
                anim.setDuration(180)
                anim.setEndValue(QPoint(x, y))
                anim.setEasingCurve(QEasingCurve.Type.OutCubic)
                anim.start(QPropertyAnimation.DeletionPolicy.DeleteWhenStopped)
            y += n.height() + GAP

    def close_all(self) -> None:
        for n in list(self.items):
            n.close()
        self.items.clear()
