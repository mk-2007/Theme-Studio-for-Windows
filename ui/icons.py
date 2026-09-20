"""Icon loading for the dock: real app icons, generated fallbacks, painted trash."""
from __future__ import annotations

import os

from PyQt6.QtCore import QFileInfo, QPointF, QRect, QRectF, QSize, Qt
from PyQt6.QtGui import (QBitmap, QColor, QFont, QLinearGradient, QPainter, QPainterPath,
                         QPen, QPixmap, QRegion)
from PyQt6.QtWidgets import QFileIconProvider

CACHE_SIZE = 128


def letter_pixmap(name: str, size: int = CACHE_SIZE) -> QPixmap:
    """Fallback icon: colored rounded square with the app's first letter."""
    hue = sum(ord(c) for c in name) * 37 % 360
    base = QColor.fromHsv(hue, 150, 215)
    pm = QPixmap(size, size)
    pm.fill(Qt.GlobalColor.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    p.setRenderHint(QPainter.RenderHint.TextAntialiasing)
    grad = QLinearGradient(0, 0, 0, size)
    grad.setColorAt(0, base.lighter(125))
    grad.setColorAt(1, base.darker(130))
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(grad)
    p.drawRoundedRect(QRectF(4, 4, size - 8, size - 8), size * 0.23, size * 0.23)
    font = QFont()
    font.setPixelSize(int(size * 0.5))
    font.setWeight(QFont.Weight.DemiBold)
    p.setFont(font)
    p.setPen(QColor(255, 255, 255, 240))
    p.drawText(QRectF(0, 0, size, size), Qt.AlignmentFlag.AlignCenter,
               (name.strip()[:1] or "?").upper())
    p.end()
    return pm


def _autocrop_if_padded(pm: QPixmap) -> QPixmap:
    """Windows' 256px shell icon can be a small icon floating in a big transparent square."""
    if pm.isNull() or pm.width() < 64:
        return pm
    mask = QBitmap.fromImage(pm.toImage().createAlphaMask())
    box = QRegion(mask).boundingRect()
    if box.isEmpty():
        return pm
    if box.width() < pm.width() * 0.72 or box.height() < pm.height() * 0.72:
        side = max(box.width(), box.height())
        square = QRect(0, 0, side, side)
        square.moveCenter(box.center())
        return pm.copy(square)
    return pm


def _squircle(rect: QRectF) -> QPainterPath:
    path = QPainterPath()
    path.addRoundedRect(rect, rect.width() * 0.225, rect.height() * 0.225)
    return path


def _is_full_bleed(img) -> bool:
    w, h = img.width(), img.height()
    pts = [(3, 3), (w - 4, 3), (3, h - 4), (w - 4, h - 4)]
    return all(img.pixelColor(x, y).alpha() > 200 for x, y in pts)


def plate_pixmap(src: QPixmap, size: int = CACHE_SIZE) -> QPixmap:
    """macOS-style icon: full-bleed art is clipped to a squircle, everything else sits on a light plate."""
    out = QPixmap(size, size)
    out.fill(Qt.GlobalColor.transparent)
    p = QPainter(out)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
    body = QRectF(5, 5, size - 10, size - 10)
    path = _squircle(body)
    if _is_full_bleed(src.toImage()):
        p.setClipPath(path)
        p.drawPixmap(body, src, QRectF(src.rect()))
    else:
        for i, alpha in enumerate((14, 10, 6)):        # soft shadow
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QColor(0, 0, 0, alpha))
            p.drawPath(_squircle(body.adjusted(-i, i + 1, i, i + 3)))
        grad = QLinearGradient(body.topLeft(), body.bottomLeft())
        grad.setColorAt(0, QColor(255, 255, 255))
        grad.setColorAt(1, QColor(226, 230, 238))
        p.setPen(QPen(QColor(0, 0, 0, 34), 1.5))
        p.setBrush(grad)
        p.drawPath(path)
        inset = body.width() * 0.17
        p.drawPixmap(body.adjusted(inset, inset, -inset, -inset), src, QRectF(src.rect()))
    p.end()
    return out


class IconCache:
    def __init__(self) -> None:
        self._provider = QFileIconProvider()
        self._cache: dict[tuple[str, str], QPixmap] = {}
        self.style = "native"          # "native" | "plate"

    def set_style(self, style: str) -> None:
        if style != self.style:
            self.style = style
            self._cache.clear()

    def get(self, path: str, name: str, request: int = 256) -> QPixmap:
        key = (f"{path.lower()}@{request}", "" if path else name)
        hit = self._cache.get(key)
        if hit is not None:
            return hit
        pm: QPixmap | None = None
        if path and os.path.exists(path):
            icon = self._provider.icon(QFileInfo(path))
            pm = icon.pixmap(QSize(request, request))
            if pm.isNull() or pm.width() < 16:
                pm = None
            else:
                pm = _autocrop_if_padded(pm)
                if pm.width() > CACHE_SIZE:
                    pm = pm.scaled(CACHE_SIZE, CACHE_SIZE, Qt.AspectRatioMode.KeepAspectRatio,
                                   Qt.TransformationMode.SmoothTransformation)
                if self.style == "plate":
                    pm = plate_pixmap(pm)
        if pm is None:
            pm = letter_pixmap(name)
        self._cache[key] = pm
        return pm


def paint_trash(p: QPainter, r: QRectF, full: bool, color: QColor) -> None:
    """A glassy trash bin drawn with the theme's text color."""
    p.save()
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    s = r.width()
    cx = r.center().x()
    top = r.top() + s * 0.30
    bottom = r.bottom() - s * 0.08

    body = QPainterPath()
    body.moveTo(cx - s * 0.27, top + s * 0.09)
    body.lineTo(cx + s * 0.27, top + s * 0.09)
    body.lineTo(cx + s * 0.22, bottom)
    body.lineTo(cx - s * 0.22, bottom)
    body.closeSubpath()

    fill = QColor(color)
    fill.setAlpha(45)
    stroke = QColor(color)
    stroke.setAlpha(200)
    p.setBrush(fill)
    p.setPen(QPen(stroke, max(1.4, s * 0.045), Qt.PenStyle.SolidLine,
                  Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin))
    p.drawPath(body)

    rib = QColor(color)
    rib.setAlpha(110)
    p.setPen(QPen(rib, max(1.0, s * 0.03), Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
    for dx in (-0.10, 0.0, 0.10):
        p.drawLine(QPointF(cx + s * dx, top + s * 0.20), QPointF(cx + s * dx * 0.9, bottom - s * 0.09))

    p.setPen(QPen(stroke, max(1.4, s * 0.045), Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
    p.setBrush(fill)
    p.drawRoundedRect(QRectF(cx - s * 0.31, top + s * 0.01, s * 0.62, s * 0.075), s * 0.03, s * 0.03)
    p.drawRoundedRect(QRectF(cx - s * 0.08, top - s * 0.04, s * 0.16, s * 0.055), s * 0.02, s * 0.02)

    if full:  # paper sticking out
        paper = QColor(255, 255, 255, 215)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(paper)
        for dx, rot in ((-0.12, -14), (0.05, 9)):
            p.save()
            p.translate(cx + s * dx, top - s * 0.02)
            p.rotate(rot)
            p.drawRoundedRect(QRectF(-s * 0.08, -s * 0.14, s * 0.16, s * 0.15), 2, 2)
            p.restore()
    p.restore()


def glyph_pixmap(char: str, hue: int, size: int = CACHE_SIZE) -> QPixmap:
    """Colored rounded square with a symbol - used for Spotlight commands/calc/web rows."""
    base = QColor.fromHsv(hue % 360, 170, 215)
    pm = QPixmap(size, size)
    pm.fill(Qt.GlobalColor.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    p.setRenderHint(QPainter.RenderHint.TextAntialiasing)
    grad = QLinearGradient(0, 0, 0, size)
    grad.setColorAt(0, base.lighter(120))
    grad.setColorAt(1, base.darker(125))
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(grad)
    p.drawRoundedRect(QRectF(4, 4, size - 8, size - 8), size * 0.23, size * 0.23)
    font = QFont()
    font.setPixelSize(int(size * 0.52))
    font.setWeight(QFont.Weight.DemiBold)
    p.setFont(font)
    p.setPen(QColor(255, 255, 255, 245))
    p.drawText(QRectF(0, 0, size, size), Qt.AlignmentFlag.AlignCenter, char)
    p.end()
    return pm


def paint_launchpad(p: QPainter, r: QRectF) -> None:
    """Launchpad dock icon: dark glass tile with a 3x3 grid of colored dots."""
    p.save()
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    s = r.width()
    grad = QLinearGradient(r.topLeft(), r.bottomLeft())
    grad.setColorAt(0, QColor(120, 128, 150))
    grad.setColorAt(1, QColor(52, 56, 72))
    p.setPen(QPen(QColor(255, 255, 255, 60), 1))
    p.setBrush(grad)
    p.drawRoundedRect(r.adjusted(1, 1, -1, -1), s * 0.23, s * 0.23)
    hues = (0, 28, 52, 120, 170, 210, 250, 285, 330)
    p.setPen(Qt.PenStyle.NoPen)
    for i, hue in enumerate(hues):
        col, row = i % 3, i // 3
        p.setBrush(QColor.fromHsv(hue, 190, 245))
        p.drawEllipse(QPointF(r.left() + s * (0.27 + 0.23 * col), r.top() + s * (0.27 + 0.23 * row)),
                      s * 0.075, s * 0.075)
    p.restore()
