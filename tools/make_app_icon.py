from __future__ import annotations

import struct
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
from PySide6.QtCore import QBuffer, QByteArray, QIODevice, QRect, Qt
from PySide6.QtGui import QColor, QGuiApplication, QImage, QPainter

SIZES = (16, 20, 24, 32, 40, 48, 64, 96, 128, 256)


def unwhite(src: QImage) -> QImage:
    img = src.convertToFormat(QImage.Format.Format_ARGB32)
    w, h = img.width(), img.height()
    ink = min((QColor(img.pixel(x, y)) for x in range(0, w, 4) for y in range(0, h, 4)),
              key=lambda c: c.blue())
    span = max(1, 255 - ink.blue())
    out = QImage(w, h, QImage.Format.Format_ARGB32)
    for y in range(h):
        for x in range(w):
            c = QColor(img.pixel(x, y))
            a = max(0.0, min(1.0, (255 - c.blue()) / span)) * (c.alpha() / 255)
            out.setPixelColor(x, y, QColor(ink.red(), ink.green(), ink.blue(), int(round(a * 255))))
    return out


def crop_square(img: QImage, margin: float = 0.04) -> QImage:
    w, h = img.width(), img.height()
    xs, ys = [], []
    for y in range(0, h, 2):
        for x in range(0, w, 2):
            if img.pixelColor(x, y).alpha() > 8:
                xs.append(x)
                ys.append(y)
    box = QRect(min(xs), min(ys), max(xs) - min(xs) + 2, max(ys) - min(ys) + 2)
    side = int(max(box.width(), box.height()) * (1 + 2 * margin))
    sq = QImage(side, side, QImage.Format.Format_ARGB32)
    sq.fill(Qt.GlobalColor.transparent)
    p = QPainter(sq)
    p.drawImage((side - box.width()) // 2, (side - box.height()) // 2, img.copy(box))
    p.end()
    return sq


def png_bytes(img: QImage) -> bytes:
    ba = QByteArray()
    buf = QBuffer(ba)
    buf.open(QIODevice.OpenModeFlag.WriteOnly)
    img.save(buf, "PNG")
    return bytes(ba)


def write_ico(path: Path, master: QImage) -> None:
    entries = []
    for s in SIZES:
        im = master.scaled(s, s, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)
        entries.append((s, png_bytes(im)))
    head = struct.pack("<HHH", 0, 1, len(entries))
    offset = 6 + 16 * len(entries)
    table, data = b"", b""
    for s, png in entries:
        d = 0 if s >= 256 else s
        table += struct.pack("<BBBBHHII", d, d, 0, 0, 1, 32, len(png), offset + len(data))
        data += png
    path.write_bytes(head + table + data)


def main() -> None:
    QGuiApplication(sys.argv[:1])
    src = QImage(sys.argv[1])
    if src.isNull():
        raise SystemExit("could not read " + sys.argv[1])
    art = src.convertToFormat(QImage.Format.Format_ARGB32) if src.hasAlphaChannel() else unwhite(src)
    master = crop_square(art).scaled(512, 512, Qt.AspectRatioMode.KeepAspectRatio,
                                               Qt.TransformationMode.SmoothTransformation)
    (ROOT / "assets" / "ui").mkdir(parents=True, exist_ok=True)
    master.save(str(ROOT / "assets" / "ui" / "app_icon.png"))
    (ROOT / "assets" / "icons").mkdir(parents=True, exist_ok=True)
    write_ico(ROOT / "assets" / "icons" / "voxagen.ico", master)
    print("ok", master.width())


if __name__ == "__main__":
    main()
