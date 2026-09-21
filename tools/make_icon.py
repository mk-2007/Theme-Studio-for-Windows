"""Generates assets/theme_studio.ico (run once; the .ico is already included)."""
import os
import struct
import sys

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from PyQt6.QtCore import QBuffer, QByteArray, QIODevice, QPointF, QRectF, Qt
from PyQt6.QtGui import QColor, QGuiApplication, QImage, QLinearGradient, QPainter, QPainterPath, QPen, QRadialGradient

app = QGuiApplication(sys.argv)


def render(size: int) -> QImage:
    img = QImage(size, size, QImage.Format.Format_ARGB32)
    img.fill(Qt.GlobalColor.transparent)
    p = QPainter(img)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    m = size * 0.04
    body = QRectF(m, m, size - 2 * m, size - 2 * m)
    path = QPainterPath()
    path.addRoundedRect(body, size * 0.225, size * 0.225)
    g = QLinearGradient(body.topLeft(), body.bottomRight())
    g.setColorAt(0, QColor(88, 120, 255))
    g.setColorAt(0.55, QColor(120, 78, 235))
    g.setColorAt(1, QColor(214, 84, 180))
    p.fillPath(path, g)
    gloss = QLinearGradient(body.topLeft(), body.bottomLeft())
    gloss.setColorAt(0, QColor(255, 255, 255, 110))
    gloss.setColorAt(0.5, QColor(255, 255, 255, 0))
    p.fillPath(path, gloss)
    p.setPen(QPen(QColor(255, 255, 255, 90), max(1.0, size / 128)))
    p.setBrush(Qt.BrushStyle.NoBrush)
    p.drawPath(path)
    # glass orb
    c = QPointF(size / 2, size / 2)
    r = size * 0.27
    orb = QRadialGradient(QPointF(c.x() - r * 0.3, c.y() - r * 0.4), r * 1.5)
    orb.setColorAt(0, QColor(255, 255, 255, 250))
    orb.setColorAt(0.35, QColor(190, 220, 255, 235))
    orb.setColorAt(1, QColor(60, 90, 220, 235))
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(orb)
    p.drawEllipse(c, r, r)
    p.setPen(QPen(QColor(255, 255, 255, 120), max(1.0, size / 100)))
    p.setBrush(Qt.BrushStyle.NoBrush)
    p.drawEllipse(c, r - 0.5, r - 0.5)
    p.end()
    return img


sizes = [16, 24, 32, 48, 64, 128, 256]
blobs = []
for s in sizes:
    ba = QByteArray()
    buf = QBuffer(ba)
    buf.open(QIODevice.OpenModeFlag.WriteOnly)
    render(s).save(buf, "PNG")
    blobs.append(bytes(ba))

out_dir = os.path.join(os.path.dirname(__file__), "..", "assets")
os.makedirs(out_dir, exist_ok=True)
header = struct.pack("<HHH", 0, 1, len(sizes))
offset = 6 + 16 * len(sizes)
entries = b""
for s, blob in zip(sizes, blobs):
    entries += struct.pack("<BBBBHHII", 0 if s >= 256 else s, 0 if s >= 256 else s, 0, 0, 1, 32, len(blob), offset)
    offset += len(blob)
with open(os.path.join(out_dir, "theme_studio.ico"), "wb") as f:
    f.write(header + entries + b"".join(blobs))
render(256).save(os.path.join(out_dir, "theme_studio.png"))
print("wrote assets/theme_studio.ico")
