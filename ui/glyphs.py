"""Vector glyphs (Wi-Fi, moon, speaker, ...) drawn with QPainter so they scale and theme."""
from __future__ import annotations

import math

from PyQt6.QtCore import QPointF, QRectF, Qt
from PyQt6.QtGui import QColor, QPainter, QPainterPath, QPen


def _pen(color: QColor, w: float) -> QPen:
    return QPen(color, w, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin)


def _begin(p: QPainter) -> None:
    p.save()
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    p.setBrush(Qt.BrushStyle.NoBrush)


def draw_wifi(p: QPainter, r: QRectF, c: QColor) -> None:
    _begin(p)
    s, cx, by = r.width(), r.center().x(), r.top() + r.width() * 0.84
    p.setPen(_pen(c, s * 0.10))
    for rad in (0.22, 0.44, 0.66):
        R = s * rad
        p.drawArc(QRectF(cx - R, by - R, 2 * R, 2 * R), 45 * 16, 90 * 16)
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(c)
    p.drawEllipse(QPointF(cx, by), s * 0.07, s * 0.07)
    p.restore()


def draw_bluetooth(p: QPainter, r: QRectF, c: QColor) -> None:
    _begin(p)
    pts = [(0.27, 0.30), (0.73, 0.70), (0.50, 0.92), (0.50, 0.08), (0.73, 0.30), (0.27, 0.70)]
    path = QPainterPath(QPointF(r.left() + pts[0][0] * r.width(), r.top() + pts[0][1] * r.height()))
    for x, y in pts[1:]:
        path.lineTo(r.left() + x * r.width(), r.top() + y * r.height())
    p.setPen(_pen(c, r.width() * 0.09))
    p.drawPath(path)
    p.restore()


def draw_moon(p: QPainter, r: QRectF, c: QColor) -> None:
    _begin(p)
    s = r.width()
    disc = QPainterPath()
    disc.addEllipse(r.center(), s * 0.36, s * 0.36)
    bite = QPainterPath()
    bite.addEllipse(QPointF(r.center().x() + s * 0.17, r.center().y() - s * 0.12), s * 0.31, s * 0.31)
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(c)
    p.drawPath(disc.subtracted(bite))
    p.restore()


def draw_sun(p: QPainter, r: QRectF, c: QColor) -> None:
    _begin(p)
    s, ctr = r.width(), r.center()
    p.setPen(_pen(c, s * 0.08))
    p.drawEllipse(ctr, s * 0.17, s * 0.17)
    for i in range(8):
        a = i * math.pi / 4
        p.drawLine(QPointF(ctr.x() + math.cos(a) * s * 0.27, ctr.y() + math.sin(a) * s * 0.27),
                   QPointF(ctr.x() + math.cos(a) * s * 0.40, ctr.y() + math.sin(a) * s * 0.40))
    p.restore()


def draw_contrast(p: QPainter, r: QRectF, c: QColor) -> None:
    _begin(p)
    s = r.width()
    box = QRectF(r.center().x() - s * 0.34, r.center().y() - s * 0.34, s * 0.68, s * 0.68)
    p.setPen(_pen(c, s * 0.08))
    p.drawEllipse(box)
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(c)
    p.drawPie(box, 90 * 16, 180 * 16)
    p.restore()


def draw_speaker(p: QPainter, r: QRectF, c: QColor, level: float = 1.0, muted: bool = False) -> None:
    _begin(p)
    s, x0, y0 = r.width(), r.left(), r.top()
    body = QPainterPath(QPointF(x0 + s * .14, y0 + s * .38))
    for x, y in ((.30, .38), (.50, .20), (.50, .80), (.30, .62), (.14, .62)):
        body.lineTo(x0 + s * x, y0 + s * y)
    body.closeSubpath()
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(c)
    p.drawPath(body)
    p.setBrush(Qt.BrushStyle.NoBrush)
    p.setPen(_pen(c, s * 0.08))
    if muted:
        p.drawLine(QPointF(x0 + s * .64, y0 + s * .38), QPointF(x0 + s * .88, y0 + s * .62))
        p.drawLine(QPointF(x0 + s * .88, y0 + s * .38), QPointF(x0 + s * .64, y0 + s * .62))
    else:
        for i, rad in enumerate((.16, .30)):
            if level > 0.25 + i * 0.4:
                R = s * rad
                cx, cy = x0 + s * .50, y0 + s * .50
                p.drawArc(QRectF(cx - R, cy - R, 2 * R, 2 * R), -45 * 16, 90 * 16)
    p.restore()


def draw_play(p: QPainter, r: QRectF, c: QColor) -> None:
    _begin(p)
    s = r.width()
    path = QPainterPath(QPointF(r.left() + s * .32, r.top() + s * .22))
    path.lineTo(r.left() + s * .78, r.top() + s * .50)
    path.lineTo(r.left() + s * .32, r.top() + s * .78)
    path.closeSubpath()
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(c)
    p.drawPath(path)
    p.restore()


def draw_skip(p: QPainter, r: QRectF, c: QColor, forward: bool = True) -> None:
    _begin(p)
    s = r.width()
    flip = 1 if forward else -1
    cx = r.center().x()

    def X(dx: float) -> float:
        return cx + flip * s * dx

    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(c)
    for off in (-0.02, 0.22):
        tri = QPainterPath(QPointF(X(off - .26), r.top() + s * .28))
        tri.lineTo(X(off + .02), r.top() + s * .50)
        tri.lineTo(X(off - .26), r.top() + s * .72)
        tri.closeSubpath()
        p.drawPath(tri)
    p.restore()


def draw_search(p: QPainter, r: QRectF, c: QColor) -> None:
    _begin(p)
    s = r.width()
    p.setPen(_pen(c, s * 0.10))
    p.drawEllipse(QPointF(r.left() + s * .44, r.top() + s * .44), s * .24, s * .24)
    p.drawLine(QPointF(r.left() + s * .62, r.top() + s * .62), QPointF(r.left() + s * .82, r.top() + s * .82))
    p.restore()


def draw_controls(p: QPainter, r: QRectF, c: QColor) -> None:
    """Control Center icon: two little toggle switches."""
    _begin(p)
    s = r.width()
    p.setPen(_pen(c, s * 0.075))
    for row, knob_right in ((0.32, True), (0.68, False)):
        y = r.top() + s * row
        p.drawRoundedRect(QRectF(r.left() + s * .12, y - s * .10, s * .76, s * .20), s * .10, s * .10)
        p.setBrush(c)
        p.drawEllipse(QPointF(r.left() + s * (.70 if knob_right else .30), y), s * .075, s * .075)
        p.setBrush(Qt.BrushStyle.NoBrush)
    p.restore()


def draw_widgets(p: QPainter, r: QRectF, c: QColor) -> None:
    _begin(p)
    s = r.width()
    p.setPen(_pen(c, s * 0.08))
    for x, y in ((.18, .18), (.54, .18), (.18, .54), (.54, .54)):
        p.drawRoundedRect(QRectF(r.left() + s * x, r.top() + s * y, s * .28, s * .28), s * .06, s * .06)
    p.restore()


def draw_power(p: QPainter, r: QRectF, c: QColor) -> None:
    _begin(p)
    s, ctr = r.width(), r.center()
    p.setPen(_pen(c, s * 0.10))
    R = s * 0.34
    p.drawArc(QRectF(ctr.x() - R, ctr.y() - R + s * 0.04, 2 * R, 2 * R), 120 * 16, 300 * 16)
    p.drawLine(QPointF(ctr.x(), r.top() + s * 0.10), QPointF(ctr.x(), ctr.y() - s * 0.02))
    p.restore()


def draw_chevron(p: QPainter, r: QRectF, c: QColor, up: bool = True) -> None:
    _begin(p)
    s, cx = r.width(), r.center().x()
    y0, y1 = (0.62, 0.36) if up else (0.36, 0.62)
    p.setPen(_pen(c, s * 0.11))
    path = QPainterPath(QPointF(cx - s * 0.26, r.top() + s * y0))
    path.lineTo(cx, r.top() + s * y1)
    path.lineTo(cx + s * 0.26, r.top() + s * y0)
    p.drawPath(path)
    p.restore()
