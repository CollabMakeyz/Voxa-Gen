from __future__ import annotations

from functools import lru_cache

from PySide6.QtCore import QRectF, QSize, Qt, Signal
from PySide6.QtGui import QBrush, QColor, QIcon, QPainter, QPixmap
from PySide6.QtWidgets import QSizePolicy, QVBoxLayout, QWidget

from ...paths import assets_dir
from ...i18n import tr
from .. import theme

UI_ASSETS = "ui"
NAV_ICON_SIZE = QSize(29, 31)
PANEL_INSET = 16
PANEL_RADIUS = 19
PANEL_TOP = 22
TAB_W, TAB_H, TAB_GAP, TAB_TOP = 143, 18, 7, 4
DOT_PITCH = 10


def ui_asset(name: str) -> str:
    return str(assets_dir() / UI_ASSETS / name)


HAND_NAV = {"generator": "nav_generate", "lab": "nav_lab", "presets": "nav_presets",
            "samples": "nav_samples", "settings": "nav_settings", "appearance": "nav_appearance"}
LINE_NAV = {"generator": "generator", "lab": "lab", "appearance": "palette", "settings": "settings",
            "presets": "presets", "samples": "samples"}


def nav_icon(page_id: str) -> QIcon:
    if theme.look().icon_style == "hand" and page_id in HAND_NAV:
        return _hand_nav(page_id)
    from .. import icons
    return icons.icon(LINE_NAV.get(page_id, "info"), size=28)


@lru_cache(maxsize=16)
def _hand_nav(page_id: str) -> QIcon:
    return QIcon(QPixmap(ui_asset(f"{HAND_NAV[page_id]}.png")))


class LogoView(QWidget):

    WIDTH = 300

    def __init__(self, parent=None):
        super().__init__(parent)
        self.pixmap = QPixmap(ui_asset("logo.png"))
        w = self.WIDTH
        h = round(w * self.pixmap.height() / max(1, self.pixmap.width())) if not self.pixmap.isNull() else 122
        self.setFixedSize(w, h)
        self.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        self.setToolTip("Voxa GEN")

    def paintEvent(self, _):
        if self.pixmap.isNull():
            return
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        tint = theme.current().logo
        if not tint:
            p.drawPixmap(self.rect(), self.pixmap)
            return
        img = self.pixmap.toImage().convertToFormat(self.pixmap.toImage().Format.Format_ARGB32_Premultiplied)
        tinted = QPixmap.fromImage(img)
        q = QPainter(tinted)
        q.setCompositionMode(QPainter.CompositionMode.CompositionMode_Multiply)
        q.fillRect(tinted.rect(), QColor(tint))
        q.setCompositionMode(QPainter.CompositionMode.CompositionMode_DestinationIn)
        q.drawPixmap(0, 0, self.pixmap)
        q.end()
        p.drawPixmap(self.rect(), tinted)


class FolderTabs(QWidget):
    currentChanged = Signal(int)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.labels: list[str] = []
        self.current = 0
        self._hover = -1
        self.setMouseTracking(True)
        self.setCursor(Qt.CursorShape.PointingHandCursor)

    def set_tabs(self, labels: list[str], current: int = 0) -> None:
        self.sources = list(labels)
        self.labels = [tr(l).upper() for l in labels]
        self.current = current
        self.setVisible(bool(labels))
        self.update()

    def retranslate_ui(self) -> None:
        self.labels = [tr(l).upper() for l in getattr(self, "sources", [])]
        self.update()

    def set_current(self, i: int, emit: bool = True) -> None:
        if 0 <= i < len(self.labels) and i != self.current:
            self.current = i
            self.update()
            if emit:
                self.currentChanged.emit(i)

    def _rects(self) -> list[QRectF]:
        from PySide6.QtGui import QFontMetrics
        fm = QFontMetrics(theme.tab_font(16))
        widths = [max(TAB_W, fm.horizontalAdvance(t) + 28) for t in self.labels]
        total = sum(widths) + TAB_GAP * (len(widths) - 1)
        x = (self.width() - total) / 2
        out = []
        for w in widths:
            out.append(QRectF(x, 0, w, self.height()))
            x += w + TAB_GAP
        return out

    def paintEvent(self, _):
        t = theme.current()
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setFont(theme.tab_font(16))
        for i, (r, text) in enumerate(zip(self._rects(), self.labels)):
            colour = t.tab_selected if i == self.current else (t.hover if i == self._hover else t.panel)
            path = _top_rounded(r, theme.rad(9))
            p.fillPath(path, QColor(colour))
            p.setPen(QColor(t.text))
            p.drawText(r.adjusted(0, 1, 0, 0), Qt.AlignmentFlag.AlignCenter, text)

    def mouseMoveEvent(self, e):
        h = next((i for i, r in enumerate(self._rects()) if r.contains(e.position())), -1)
        if h != self._hover:
            self._hover = h
            self.update()

    def leaveEvent(self, e):
        self._hover = -1
        self.update()

    def mousePressEvent(self, e):
        for i, r in enumerate(self._rects()):
            if r.contains(e.position()):
                self.set_current(i)


def _top_rounded(r: QRectF, radius: float):
    from PySide6.QtGui import QPainterPath
    path = QPainterPath()
    path.moveTo(r.left(), r.bottom())
    path.lineTo(r.left(), r.top() + radius)
    path.quadTo(r.left(), r.top(), r.left() + radius, r.top())
    path.lineTo(r.right() - radius, r.top())
    path.quadTo(r.right(), r.top(), r.right(), r.top() + radius)
    path.lineTo(r.right(), r.bottom())
    path.closeSubpath()
    return path


class ContentHost(QWidget):

    def __init__(self, inner: QWidget, parent=None):
        super().__init__(parent)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(PANEL_INSET, PANEL_TOP, PANEL_INSET, PANEL_INSET)
        lay.addWidget(inner)
        self.tabs = FolderTabs(self)
        self.tabs.hide()
        self._tile = None
        self._tile_theme = ""

    def resizeEvent(self, e):
        self.tabs.setGeometry(PANEL_INSET, TAB_TOP, self.width() - 2 * PANEL_INSET, TAB_H)
        super().resizeEvent(e)

    def _dots(self) -> QBrush:
        t = theme.current()
        if self._tile is None or self._tile_theme != t.name + t.dots + t.bg:
            ratio = self.devicePixelRatioF() or 1.0
            pm = QPixmap(int(DOT_PITCH * ratio), int(DOT_PITCH * ratio))
            pm.setDevicePixelRatio(ratio)
            pm.fill(QColor(t.bg))
            p = QPainter(pm)
            p.setRenderHint(QPainter.RenderHint.Antialiasing)
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QColor(t.dots))
            p.drawEllipse(QRectF(DOT_PITCH / 2 - 1.6, DOT_PITCH / 2 - 1.6, 3.2, 3.2))
            p.end()
            self._tile, self._tile_theme = pm, t.name + t.dots + t.bg
        return QBrush(self._tile)

    def paintEvent(self, _):
        t = theme.current()
        p = QPainter(self)
        p.fillRect(self.rect(), self._dots())
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(t.panel))
        r = QRectF(self.rect()).adjusted(PANEL_INSET, PANEL_TOP, -PANEL_INSET, -PANEL_INSET)
        p.drawRoundedRect(r, theme.rad(PANEL_RADIUS), theme.rad(PANEL_RADIUS))
