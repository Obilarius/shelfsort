"""Draws the ShelfSort icon (a shelf with books) and writes shelfsort/assets/icon.png + icon.ico.

Run once after changing the design:  python tools/make_icon.py
"""
from __future__ import annotations

import struct
import sys
from pathlib import Path

from PySide6.QtCore import QBuffer, QByteArray, QIODevice, QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QGuiApplication, QImage, QLinearGradient, QPainter, QPainterPath

ASSETS = Path(__file__).resolve().parent.parent / "shelfsort" / "assets"
SIZES = [16, 24, 32, 48, 64, 128, 256]


def draw(size: int) -> QImage:
    img = QImage(size, size, QImage.Format_ARGB32)
    img.fill(Qt.transparent)
    p = QPainter(img)
    p.setRenderHint(QPainter.Antialiasing)
    s = size / 256  # design on a 256 grid

    # background: rounded square with a blue gradient
    bg = QLinearGradient(QPointF(0, 0), QPointF(0, size))
    bg.setColorAt(0, QColor("#2f7cf6"))
    bg.setColorAt(1, QColor("#1b4fb8"))
    path = QPainterPath()
    path.addRoundedRect(QRectF(8 * s, 8 * s, 240 * s, 240 * s), 52 * s, 52 * s)
    p.fillPath(path, bg)

    # books standing on the shelf (x, width, height, colour); the last one leans
    shelf_y = 190 * s
    books = [(52, 34, 112, "#f2f5fb"), (90, 28, 128, "#9ec2ff"), (122, 36, 100, "#ffd166")]
    for x, w, h, col in books:
        r = QRectF(x * s, shelf_y - h * s, w * s, h * s)
        p.setPen(Qt.NoPen)
        p.setBrush(QColor(col))
        p.drawRoundedRect(r, 5 * s, 5 * s)
    p.save()
    p.translate(170 * s, shelf_y)
    p.rotate(18)
    p.setBrush(QColor("#7bd3a8"))
    p.drawRoundedRect(QRectF(0, -118 * s, 30 * s, 118 * s), 5 * s, 5 * s)
    p.restore()

    # the shelf board
    p.setBrush(QColor("#0f2f6e"))
    p.drawRoundedRect(QRectF(36 * s, shelf_y, 184 * s, 16 * s), 6 * s, 6 * s)
    p.end()
    return img


def png_bytes(img: QImage) -> bytes:
    data = QByteArray()
    buf = QBuffer(data)
    buf.open(QIODevice.WriteOnly)
    img.save(buf, "PNG")
    return bytes(data)


def write_ico(path: Path, images: list[QImage]) -> None:
    """ICO with PNG-compressed entries (supported since Windows Vista)."""
    pngs = [png_bytes(i) for i in images]
    header = struct.pack("<HHH", 0, 1, len(pngs))
    offset = 6 + 16 * len(pngs)
    entries, blobs = b"", b""
    for img, blob in zip(images, pngs):
        w = img.width() if img.width() < 256 else 0  # 0 means 256
        entries += struct.pack("<BBBBHHII", w, w, 0, 0, 1, 32, len(blob), offset + len(blobs))
        blobs += blob
    path.write_bytes(header + entries + blobs)


def main() -> None:
    app = QGuiApplication(sys.argv)  # noqa: F841 - needed for font/paint backends
    ASSETS.mkdir(parents=True, exist_ok=True)
    images = [draw(n) for n in SIZES]
    images[-1].save(str(ASSETS / "icon.png"))
    write_ico(ASSETS / "icon.ico", images)
    print(f"geschrieben: {ASSETS / 'icon.png'}, {ASSETS / 'icon.ico'}")


if __name__ == "__main__":
    main()
