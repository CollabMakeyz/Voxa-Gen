from __future__ import annotations

import numpy as np
from PySide6.QtCore import QPointF, QRectF, Qt, Signal
from PySide6.QtGui import QPainter, QPainterPath, QPen
from PySide6.QtWidgets import QSizePolicy, QWidget

from .. import theme

BINS = 4000


def envelope(x: np.ndarray | None, bins: int = BINS) -> np.ndarray | None:
    if x is None or len(x) == 0:
        return None
    m = x.mean(axis=1) if x.ndim == 2 else x
    n = len(m)
    bins = max(1, min(bins, n))
    edges = np.linspace(0, n, bins + 1).astype(int)
    mins = np.minimum.reduceat(m, edges[:-1])
    maxs = np.maximum.reduceat(m, edges[:-1])
    return np.stack([mins, maxs], axis=1)


class WaveformView(QWidget):
    seekRequested = Signal(float)
    markerClicked = Signal(int)

    def __init__(self, primary: str = "accent", height: int = 110, parent=None):
        super().__init__(parent)
        self.primary = primary
        self.setMinimumHeight(height)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.setMouseTracking(True)
        self._env = None
        self._overlay = None
        self._overlay_color = "processed"
        self.duration = 0.0
        self.position = 0.0
        self.markers: list[float] = []
        self.marker_labels: list[str] = []
        self.marker_states: list[str] = []
        self.current_marker = -1
        self._dragging = False
        self.placeholder = "No audio"
        self.label = ""

    def set_audio(self, x: np.ndarray | None, sr: int, label: str = "") -> None:
        self._env = envelope(x)
        self.duration = (len(x) / float(sr)) if x is not None and sr else 0.0
        self.label = label
        self.update()

    def set_overlay(self, x: np.ndarray | None, color: str = "processed") -> None:
        self._overlay = envelope(x)
        self._overlay_color = color
        self.update()

    def set_markers(self, seconds: list[float], labels: list[str] | None = None,
                    states: list[str] | None = None) -> None:
        self.markers = list(seconds)
        self.marker_labels = list(labels or [])
        self.marker_states = list(states or [])
        self.update()

    def set_current_marker(self, i: int) -> None:
        if i != self.current_marker:
            self.current_marker = i
            self.update()

    def set_position(self, seconds: float) -> None:
        self.position = seconds
        self.update()

    def clear(self) -> None:
        self._env = None
        self._overlay = None
        self.duration = 0.0
        self.markers = []
        self.position = 0.0
        self.update()

    def _x(self, seconds: float) -> float:
        return (seconds / self.duration) * self.width() if self.duration > 0 else 0.0

    def paintEvent(self, _):
        t = theme.current()
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        r = self.rect()
        well = QPainterPath()
        well.addRoundedRect(QRectF(r), 8, 8)
        p.setClipPath(well)
        p.fillRect(r, theme.qcolor(t.wave_bg))
        mid = r.height() / 2.0
        p.setPen(QPen(theme.qcolor(t.border), 1, Qt.PenStyle.DotLine))
        p.drawLine(QPointF(0, mid), QPointF(r.width(), mid))
        if self._env is None:
            p.setPen(theme.qcolor(t.text_faint))
            from ...i18n import tr
            p.drawText(r, Qt.AlignmentFlag.AlignCenter, tr(self.placeholder))
            return
        for i, s in enumerate(self.markers):
            x = self._x(s)
            nxt = self._x(self.markers[i + 1]) if i + 1 < len(self.markers) else r.width()
            state = self.marker_states[i] if i < len(self.marker_states) else ""
            if i == self.current_marker:
                p.fillRect(QRectF(x, 0, nxt - x, r.height()), theme.qcolor(t.accent, 34))
            elif state == "error":
                p.fillRect(QRectF(x, 0, nxt - x, r.height()), theme.qcolor(t.error, 30))
            p.setPen(QPen(theme.qcolor(t.border_strong), 1))
            p.drawLine(QPointF(x, 0), QPointF(x, r.height()))
        self._draw_env(p, self._env, theme.qcolor(getattr(t, self.primary, self.primary), 210), mid)
        if self._overlay is not None:
            self._draw_env(p, self._overlay, theme.qcolor(getattr(t, self._overlay_color, self._overlay_color), 150), mid)
        if self.markers and self.marker_labels:
            p.setPen(theme.qcolor(t.text_muted))
            f = p.font()
            f.setPointSizeF(theme.fs(7.5))
            p.setFont(f)
            last_x = -100.0
            for i, s in enumerate(self.markers):
                x = self._x(s)
                if x - last_x > 34 and i < len(self.marker_labels):
                    text = self.marker_labels[i]
                    w = p.fontMetrics().horizontalAdvance(text) + 6
                    p.fillRect(QRectF(x + 1, 1, w, 13), theme.qcolor(t.wave_bg, 220))
                    p.drawText(QPointF(x + 4, 11), text)
                    last_x = x + w
        if self.label:
            p.setPen(theme.qcolor(t.text_faint))
            p.drawText(r.adjusted(6, 0, -6, -4), Qt.AlignmentFlag.AlignBottom | Qt.AlignmentFlag.AlignLeft, self.label)
        x = self._x(self.position)
        p.setPen(QPen(theme.qcolor(t.text), 1.5))
        p.drawLine(QPointF(x, 0), QPointF(x, r.height()))

    def _draw_env(self, p: QPainter, env: np.ndarray, color, mid: float) -> None:
        w = max(1, self.width())
        n = len(env)
        cols = min(w, n)
        idx = np.linspace(0, n, cols + 1).astype(int)
        mins = np.minimum.reduceat(env[:, 0], idx[:-1])
        maxs = np.maximum.reduceat(env[:, 1], idx[:-1])
        xs = np.linspace(0, w, cols)
        amp = mid * 0.92
        path = QPainterPath()
        path.moveTo(xs[0], mid - maxs[0] * amp)
        for x, v in zip(xs[1:], maxs[1:]):
            path.lineTo(x, mid - v * amp)
        for x, v in zip(xs[::-1], mins[::-1]):
            path.lineTo(x, mid - v * amp)
        path.closeSubpath()
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(color)
        p.drawPath(path)

    def _seconds_at(self, x: float) -> float:
        return max(0.0, min(self.duration, x / max(1, self.width()) * self.duration))

    def mousePressEvent(self, e):
        if e.button() == Qt.MouseButton.LeftButton and self.duration > 0:
            self._dragging = True
            s = self._seconds_at(e.position().x())
            self.position = s
            self.seekRequested.emit(s)
            if self.markers:
                idx = max([i for i, m in enumerate(self.markers) if m <= s] or [0])
                self.markerClicked.emit(idx)
            self.update()

    def mouseMoveEvent(self, e):
        if self._dragging:
            s = self._seconds_at(e.position().x())
            self.position = s
            self.seekRequested.emit(s)
            self.update()
        elif self.markers and self.duration > 0:
            s = self._seconds_at(e.position().x())
            idx = max([i for i, m in enumerate(self.markers) if m <= s] or [0])
            if idx < len(self.marker_labels):
                self.setToolTip(self.marker_labels[idx])

    def mouseReleaseEvent(self, e):
        self._dragging = False


class SpectrogramView(QWidget):

    def __init__(self, height: int = 140, parent=None):
        super().__init__(parent)
        self.setMinimumHeight(height)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self._img = None
        self.duration = 0.0
        self.position = 0.0
        self.label = ""

    def set_audio(self, x: np.ndarray | None, sr: int, label: str = "") -> None:
        self.label = label
        if x is None or len(x) < 512:
            self._img = None
            self.update()
            return
        from scipy.signal import stft
        from PySide6.QtGui import QImage
        m = x.mean(axis=1) if x.ndim == 2 else x
        self.duration = len(m) / float(sr)
        nper = 2048 if sr > 32000 else 1024
        f, _, z = stft(m, sr, nperseg=nper, noverlap=nper - nper // 4, boundary=None)
        mag = 20 * np.log10(np.abs(z) + 1e-9)
        mag = np.clip((mag - mag.max() + 90) / 90.0, 0, 1)
        rows = 256
        lf = np.geomspace(50, sr / 2, rows)
        idx = np.clip(np.searchsorted(f, lf), 0, len(f) - 1)
        img = mag[idx][::-1]
        lut = self._lut()
        rgb = lut[(img * 255).astype(np.uint8)]
        h, w = rgb.shape[:2]
        rgba = np.concatenate([rgb, np.full((h, w, 1), 255, np.uint8)], axis=2)
        self._buf = np.ascontiguousarray(rgba)
        self._img = QImage(self._buf.data, w, h, 4 * w, QImage.Format.Format_RGBA8888)
        self.update()

    def _lut(self) -> np.ndarray:
        t = theme.current()
        stops = [theme.qcolor(t.wave_bg), theme.qcolor("#1d3557" if t.name == "dark" else "#cfe3ea"),
                 theme.qcolor(t.processed), theme.qcolor(t.accent), theme.qcolor("#fff4dc" if t.name == "dark" else "#7a3d00")]
        pts = np.linspace(0, 255, len(stops))
        out = np.zeros((256, 3), np.uint8)
        for c, comp in enumerate(("red", "green", "blue")):
            vals = [getattr(s, comp)() for s in stops]
            out[:, c] = np.interp(np.arange(256), pts, vals).astype(np.uint8)
        return out

    def set_position(self, seconds: float) -> None:
        self.position = seconds
        self.update()

    def paintEvent(self, _):
        t = theme.current()
        p = QPainter(self)
        r = self.rect()
        well = QPainterPath()
        well.addRoundedRect(QRectF(r), 8, 8)
        p.setClipPath(well)
        p.fillRect(r, theme.qcolor(t.wave_bg))
        if self._img is None:
            p.setPen(theme.qcolor(t.text_faint))
            from ...i18n import tr
            p.drawText(r, Qt.AlignmentFlag.AlignCenter, tr("No spectrum"))
        else:
            p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, True)
            p.drawImage(QRectF(r), self._img)
            if self.duration > 0:
                x = self.position / self.duration * r.width()
                p.setPen(QPen(theme.qcolor(t.text), 1.2))
                p.drawLine(QPointF(x, 0), QPointF(x, r.height()))
        if self.label:
            p.setPen(theme.qcolor(t.text))
            p.drawText(r.adjusted(6, 4, -6, -4), Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft, self.label)
