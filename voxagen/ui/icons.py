from __future__ import annotations

from functools import lru_cache

from PySide6.QtCore import QByteArray, QRectF, Qt
from PySide6.QtGui import QIcon, QImage, QPainter, QPixmap
from PySide6.QtSvg import QSvgRenderer

from . import theme

_P = {
    "generator": '<path d="M3 12h3l2-6 4 12 3-9 2 3h4"/>',
    "lab": '<path d="M9 3h6M10 3v6l-5.5 9.5A1.7 1.7 0 0 0 6 21h12a1.7 1.7 0 0 0 1.5-2.5L14 9V3"/><path d="M7.5 15h9"/>',
    "presets": '<rect x="4" y="4" width="7" height="7" rx="1.5"/><rect x="13" y="4" width="7" height="7" rx="1.5"/>'
               '<rect x="4" y="13" width="7" height="7" rx="1.5"/><path d="M16.5 13v7M13 16.5h7"/>',
    "samples": '<path d="M4 7h16M4 12h10M4 17h7"/><circle cx="17.5" cy="16.5" r="2.5"/><path d="M20 16.5V9"/>',
    "settings": '<circle cx="12" cy="12" r="3"/><path d="M12 2.5v3M12 18.5v3M4.2 7l2.6 1.5M17.2 15.5l2.6 1.5M4.2 17l2.6-1.5M17.2 8.5 19.8 7"/>',
    "play": '<path d="M7 4.5v15l12-7.5z" fill="currentColor"/>',
    "pause": '<rect x="6" y="4.5" width="4" height="15" rx="1" fill="currentColor"/><rect x="14" y="4.5" width="4" height="15" rx="1" fill="currentColor"/>',
    "stop": '<rect x="5.5" y="5.5" width="13" height="13" rx="1.5" fill="currentColor"/>',
    "restart": '<path d="M4 12a8 8 0 1 0 2.4-5.7"/><path d="M4 4v4h4"/>',
    "loop": '<path d="M17 2.5 20 5.5 17 8.5"/><path d="M4 11.5V10a4.5 4.5 0 0 1 4.5-4.5H20"/><path d="M7 21.5 4 18.5 7 15.5"/><path d="M20 12.5V14a4.5 4.5 0 0 1-4.5 4.5H4"/>',
    "prev": '<path d="M18 5v14L8 12z" fill="currentColor"/><path d="M6 5v14"/>',
    "next": '<path d="M6 5v14l10-7z" fill="currentColor"/><path d="M18 5v14"/>',
    "add": '<path d="M12 5v14M5 12h14"/>',
    "remove": '<path d="M5 12h14"/>',
    "close": '<path d="M6 6l12 12M18 6 6 18"/>',
    "duplicate": '<rect x="8" y="8" width="12" height="12" rx="2"/><path d="M16 8V6a2 2 0 0 0-2-2H6a2 2 0 0 0-2 2v8a2 2 0 0 0 2 2h2"/>',
    "folder": '<path d="M3.5 7.5A2 2 0 0 1 5.5 5.5h4l2 2.5h7a2 2 0 0 1 2 2v7.5a2 2 0 0 1-2 2h-13a2 2 0 0 1-2-2z"/>',
    "file": '<path d="M14 3H7a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2V8z"/><path d="M14 3v5h5"/>',
    "export": '<path d="M12 15V3M7 8l5-5 5 5"/><path d="M5 14v5a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2v-5"/>',
    "import": '<path d="M12 3v12M7 10l5 5 5-5"/><path d="M5 14v5a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2v-5"/>',
    "refresh": '<path d="M20 11a8 8 0 0 0-14.5-4.5L4 8"/><path d="M4 3.5V8h4.5"/><path d="M4 13a8 8 0 0 0 14.5 4.5L20 16"/><path d="M20 20.5V16h-4.5"/>',
    "undo": '<path d="M9 14 4 9l5-5"/><path d="M4 9h10.5a5.5 5.5 0 0 1 0 11H11"/>',
    "redo": '<path d="m15 14 5-5-5-5"/><path d="M20 9H9.5a5.5 5.5 0 0 0 0 11H13"/>',
    "trash": '<path d="M4 7h16M10 11v6M14 11v6"/><path d="M6 7l1 12a2 2 0 0 0 2 2h6a2 2 0 0 0 2-2l1-12"/><path d="M9 7V4h6v3"/>',
    "edit": '<path d="M4 20h4L19 9a2.8 2.8 0 0 0-4-4L4 16z"/><path d="M13.5 6.5l4 4"/>',
    "check": '<path d="M5 12.5 10 17.5 19 7"/>',
    "warning": '<path d="M12 4 2.8 19.5h18.4z"/><path d="M12 10v4.5M12 17v.5"/>',
    "error": '<circle cx="12" cy="12" r="9"/><path d="M12 7.5v5.5M12 16v.5"/>',
    "info": '<circle cx="12" cy="12" r="9"/><path d="M12 11v5.5M12 7.5V8"/>',
    "ab": '<path d="M3.5 17 7 7l3.5 10M4.8 13.5h4.4"/><path d="M14 7h4a2.5 2.5 0 0 1 0 5h-4zM14 12h4.5a2.5 2.5 0 0 1 0 5H14z"/>',
    "wave": '<path d="M2 12h2M6 8v8M10 5v14M14 9v6M18 7v10M22 12h-2"/>',
    "spectrum": '<path d="M4 20V10M8 20V5M12 20v-7M16 20V8M20 20v-4"/>',
    "keyboard": '<rect x="2.5" y="5" width="19" height="14" rx="2"/><path d="M7 5v8M12 5v8M17 5v8"/>',
    "search": '<circle cx="11" cy="11" r="6.5"/><path d="m20 20-4.2-4.2"/>',
    "dice": '<rect x="4" y="4" width="16" height="16" rx="3"/><circle cx="9" cy="9" r="1" fill="currentColor"/><circle cx="15" cy="15" r="1" fill="currentColor"/><circle cx="15" cy="9" r="1" fill="currentColor"/><circle cx="9" cy="15" r="1" fill="currentColor"/>',
    "volume": '<path d="M4 9.5h3.5L12 5.5v13l-4.5-4H4z"/><path d="M15.5 9a4 4 0 0 1 0 6M18 6.5a7.5 7.5 0 0 1 0 11"/>',
    "mute": '<path d="M4 9.5h3.5L12 5.5v13l-4.5-4H4z"/><path d="m16 9.5 5 5M21 9.5l-5 5"/>',
    "reset": '<path d="M4 12a8 8 0 1 0 8-8"/><path d="M4 4v5h5"/><circle cx="12" cy="12" r="1.2" fill="currentColor"/>',
    "drag": '<circle cx="9" cy="6" r="1" fill="currentColor"/><circle cx="15" cy="6" r="1" fill="currentColor"/><circle cx="9" cy="12" r="1" fill="currentColor"/><circle cx="15" cy="12" r="1" fill="currentColor"/><circle cx="9" cy="18" r="1" fill="currentColor"/><circle cx="15" cy="18" r="1" fill="currentColor"/>',
    "save": '<path d="M5 3.5h11l3.5 3.5v12a1.5 1.5 0 0 1-1.5 1.5H5A1.5 1.5 0 0 1 3.5 19V5A1.5 1.5 0 0 1 5 3.5z"/><path d="M7.5 3.5v5h8v-5M7.5 20.5v-6h9v6"/>',
    "sun": '<circle cx="12" cy="12" r="4"/><path d="M12 2.5v2M12 19.5v2M2.5 12h2M19.5 12h2M5.3 5.3l1.4 1.4M17.3 17.3l1.4 1.4M5.3 18.7l1.4-1.4M17.3 6.7l1.4-1.4"/>',
    "moon": '<path d="M20 14.5A8 8 0 1 1 9.5 4a6.5 6.5 0 0 0 10.5 10.5z"/>',
    "bell": '<path d="M6 16V11a6 6 0 1 1 12 0v5l1.5 2h-15z"/><path d="M10 20.5a2 2 0 0 0 4 0"/>',
    "palette": '<path d="M12 3a9 9 0 1 0 0 18c1.2 0 2-.8 2-1.8 0-.5-.2-.9-.5-1.3-.3-.4-.5-.8-.5-1.3 0-1 .8-1.6 1.8-1.6H17a4 4 0 0 0 4-4C21 6.6 17 3 12 3z"/><circle cx="7.5" cy="11" r="1.2" fill="currentColor"/><circle cx="10" cy="7" r="1.2" fill="currentColor"/><circle cx="14.5" cy="7" r="1.2" fill="currentColor"/>',
    "sliders": '<path d="M5 4v16M12 4v16M19 4v16"/><rect x="3" y="13" width="4" height="3" rx="1" fill="currentColor"/><rect x="10" y="7" width="4" height="3" rx="1" fill="currentColor"/><rect x="17" y="15" width="4" height="3" rx="1" fill="currentColor"/>',
    "queue": '<rect x="3.5" y="4" width="17" height="4.5" rx="1.2"/><rect x="3.5" y="10" width="17" height="4.5" rx="1.2"/><path d="M3.5 18.5h10"/>',
    "project": '<path d="M4 6.5A2 2 0 0 1 6 4.5h4l2 2h6a2 2 0 0 1 2 2v9a2 2 0 0 1-2 2H6a2 2 0 0 1-2-2z"/><path d="M8 13h8M12 9v8"/>',
    "analyze": '<path d="M3 12h3l2-5 3 10 2.5-7 1.5 2"/><circle cx="17.5" cy="15.5" r="3.5"/><path d="m20 18 2 2"/>',
    "up": '<path d="M12 19V5M6 11l6-6 6 6"/>',
    "down": '<path d="M12 5v14M6 13l6 6 6-6"/>',
    "power": '<path d="M12 3v8"/><path d="M6.3 6.8a8 8 0 1 0 11.4 0"/>',
    "language": '<circle cx="12" cy="12" r="9"/><path d="M3 12h18M12 3c2.5 2.5 3.5 5.5 3.5 9s-1 6.5-3.5 9c-2.5-2.5-3.5-5.5-3.5-9s1-6.5 3.5-9z"/>',
    "cpu": '<rect x="6" y="6" width="12" height="12" rx="2"/><path d="M9 2.5v3M15 2.5v3M9 18.5v3M15 18.5v3M2.5 9h3M2.5 15h3M18.5 9h3M18.5 15h3"/>',
}


STROKES = {"hand": 2.3, "line": 1.8, "bold": 2.9}


def _svg(name: str, color: str, stroke: float = 2.3) -> bytes:
    body = _P.get(name, _P["info"]).replace("currentColor", color)
    return (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="{color}" '
            f'stroke-width="{stroke}" stroke-linecap="round" stroke-linejoin="round">{body}</svg>').encode()


def _pixmap(name: str, color: str, size: int, ratio: float) -> QPixmap:
    return _pixmap_styled(name, color, size, ratio, STROKES.get(theme.look().icon_style, 2.3))


@lru_cache(maxsize=1024)
def _pixmap_styled(name: str, color: str, size: int, ratio: float, stroke: float) -> QPixmap:
    px = int(size * ratio)
    img = QImage(px, px, QImage.Format.Format_ARGB32_Premultiplied)
    img.fill(Qt.GlobalColor.transparent)
    r = QSvgRenderer(QByteArray(_svg(name, color, stroke)))
    p = QPainter(img)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    r.render(p, QRectF(0, 0, px, px))
    p.end()
    pm = QPixmap.fromImage(img)
    pm.setDevicePixelRatio(ratio)
    return pm


HAND_DRAWN = {"folder": "icon_browse.png", "refresh": "icon_rescan.png"}


@lru_cache(maxsize=32)
def _hand_icon(file: str) -> QIcon:
    from ..paths import assets_dir
    return QIcon(QPixmap(str(assets_dir() / "ui" / file)))


def icon(name: str, color: str | None = None, size: int = 18) -> QIcon:
    if name in HAND_DRAWN and color is None and theme.look().icon_style == "hand":
        return _hand_icon(HAND_DRAWN[name])
    t = theme.current()
    normal = color or t.text
    ic = QIcon()
    for ratio in (1.0, 2.0):
        ic.addPixmap(_pixmap(name, normal, size, ratio), QIcon.Mode.Normal, QIcon.State.Off)
        ic.addPixmap(_pixmap(name, color or t.text, size, ratio), QIcon.Mode.Active, QIcon.State.Off)
        ic.addPixmap(_pixmap(name, color or t.text, size, ratio), QIcon.Mode.Normal, QIcon.State.On)
        ic.addPixmap(_pixmap(name, t.text_faint, size, ratio), QIcon.Mode.Disabled, QIcon.State.Off)
    return ic


def app_icon() -> QIcon:
    from ..paths import resource_root
    art = resource_root() / "assets" / "ui" / "app_icon.png"
    if art.exists():
        src = QPixmap(str(art))
        if not src.isNull():
            ic = QIcon()
            for size in (16, 24, 32, 48, 64, 128, 256):
                ic.addPixmap(src.scaled(size, size, Qt.AspectRatioMode.KeepAspectRatio,
                                        Qt.TransformationMode.SmoothTransformation))
            return ic
    ic = QIcon()
    for size in (16, 24, 32, 48, 64, 128, 256):
        svg = (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 64 64">'
               f'<rect x="2" y="2" width="60" height="60" rx="14" fill="#16171a"/>'
               f'<path d="M12 32h6l5-14 9 28 7-20 4 6h9" fill="none" stroke="#f0a43a" stroke-width="5" '
               f'stroke-linecap="round" stroke-linejoin="round"/></svg>').encode()
        img = QImage(size, size, QImage.Format.Format_ARGB32_Premultiplied)
        img.fill(Qt.GlobalColor.transparent)
        p = QPainter(img)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        QSvgRenderer(QByteArray(svg)).render(p, QRectF(0, 0, size, size))
        p.end()
        ic.addPixmap(QPixmap.fromImage(img))
    return ic


_pixmap.cache_clear = _pixmap_styled.cache_clear
