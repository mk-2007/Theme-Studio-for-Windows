"""Pure geometry helpers: place rectangles without overlap (no GUI needed, easy to test)."""
from __future__ import annotations

from PyQt6.QtCore import QPoint, QRect


def collides(rect: QRect, others: list[QRect], gap: int = 0) -> bool:
    grown = rect.adjusted(-gap, -gap, gap, gap)
    return any(grown.intersects(o) for o in others)


def inside(rect: QRect, area: QRect) -> bool:
    return area.contains(rect)


def clamp_into(rect: QRect, area: QRect) -> QRect:
    """Move `rect` (never resize) so it lies inside `area` as far as possible."""
    x = min(max(rect.x(), area.left()), max(area.left(), area.right() + 1 - rect.width()))
    y = min(max(rect.y(), area.top()), max(area.top(), area.bottom() + 1 - rect.height()))
    return QRect(x, y, rect.width(), rect.height())


def find_free_spot(width: int, height: int, area: QRect, others: list[QRect],
                   gap: int = 14, step: int = 8) -> QPoint | None:
    """Top-right-first scan for a spot inside `area` that overlaps none of `others`."""
    if width > area.width() or height > area.height():
        return None
    y = area.top()
    while y + height <= area.bottom() + 1:
        x = area.right() + 1 - width
        while x >= area.left():
            if not collides(QRect(x, y, width, height), others, gap):
                return QPoint(x, y)
            x -= step
        y += step
    return None
