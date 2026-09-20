"""Reusable menu-bar widgets: buttons, logo orb, battery indicator, themed menu."""
from __future__ import annotations

from PyQt6.QtCore import QPointF, QRectF, QSize, Qt, pyqtSignal
from PyQt6.QtGui import (QColor, QFontMetrics, QIcon, QPainter, QPen, QPixmap,
                         QRadialGradient)
from PyQt6.QtWidgets import QMenu, QSizePolicy, QWidget

from core.theme import ThemeManager


def paint_orb(p: QPainter, center: QPointF, radius: float, accent: QColor) -> None:
    """The Theme Studio logo: a small glass gem."""
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    grad = QRadialGradient(QPointF(center.x() - radius * 0.3, center.y() - radius * 0.4), radius * 1.4)
    grad.setColorAt(0.0, QColor(255, 255, 255, 235))
    grad.setColorAt(0.35, accent.lighter(150))
    grad.setColorAt(1.0, accent.darker(140))
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(grad)
    p.drawEllipse(center, radius, radius)
    p.setBrush(Qt.BrushStyle.NoBrush)
    p.setPen(QPen(QColor(255, 255, 255, 70), 1))
    p.drawEllipse(center, radius - 0.5, radius - 0.5)


def make_logo_icon(accent: QColor, size: int = 64) -> QIcon:
    pm = QPixmap(size, size)
    pm.fill(Qt.GlobalColor.transparent)
    p = QPainter(pm)
    paint_orb(p, QPointF(size / 2, size / 2), size * 0.42, accent)
    p.end()
    return QIcon(pm)


class BarButton(QWidget):
    """Flat menu-bar item with a rounded hover highlight."""

    clicked = pyqtSignal()

    def __init__(self, tm: ThemeManager, text: str = "", bold: bool = False,
                 interactive: bool = True, pad: int = 10, parent=None):
        super().__init__(parent)
        self._tm = tm
        self._text = text
        self._bold = bold
        self._interactive = interactive
        self._pad = pad
        self._hover = False
        self._pressed = False
        self.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Expanding)
        tm.changed.connect(self._theme_changed)

    # -- API
    def text(self) -> str:
        return self._text

    def setText(self, text: str) -> None:
        if text != self._text:
            self._text = text
            self.updateGeometry()
            self.update()

    # -- sizing
    def _font(self):
        return self._tm.font(bold=self._bold)

    def content_width(self) -> int:
        return QFontMetrics(self._font()).horizontalAdvance(self._text)

    def sizeHint(self) -> QSize:
        return QSize(self.content_width() + 2 * self._pad, self._tm.theme.metric("bar_height", 28))

    def _theme_changed(self) -> None:
        self.updateGeometry()
        self.update()

    # -- painting
    def paintEvent(self, _event) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setRenderHint(QPainter.RenderHint.TextAntialiasing)
        theme = self._tm.theme
        if self._interactive and (self._hover or self._pressed):
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(theme.color("bar_pressed" if self._pressed else "bar_hover"))
            p.drawRoundedRect(QRectF(self.rect()).adjusted(1, 3, -1, -3), 5, 5)
        self.paint_content(p, QRectF(self.rect()))

    def paint_content(self, p: QPainter, rect: QRectF) -> None:
        p.setFont(self._font())
        p.setPen(self._tm.theme.color("bar_text"))
        p.drawText(rect, Qt.AlignmentFlag.AlignCenter, self._text)

    # -- input
    def enterEvent(self, _event) -> None:
        self._hover = True
        self.update()

    def leaveEvent(self, _event) -> None:
        self._hover = False
        self._pressed = False
        self.update()

    def mousePressEvent(self, event) -> None:
        if self._interactive and event.button() == Qt.MouseButton.LeftButton:
            self._pressed = True
            self.update()

    def mouseReleaseEvent(self, event) -> None:
        was_pressed = self._pressed
        self._pressed = False
        self.update()
        if was_pressed and self.rect().contains(event.position().toPoint()):
            self.clicked.emit()


class GlyphButton(BarButton):
    """Menu-bar button that draws a vector glyph instead of text."""

    def __init__(self, tm: ThemeManager, painter, parent=None):
        super().__init__(tm, "", pad=8, parent=parent)
        self._painter = painter

    def content_width(self) -> int:
        return 16

    def paint_content(self, p: QPainter, rect: QRectF) -> None:
        size = 15.0
        self._painter(p, QRectF(rect.center().x() - size / 2, rect.center().y() - size / 2, size, size),
                      self._tm.theme.color("bar_text"))


class LogoButton(BarButton):
    def __init__(self, tm: ThemeManager, parent=None):
        super().__init__(tm, "", pad=11, parent=parent)

    def content_width(self) -> int:
        return 16

    def paint_content(self, p: QPainter, rect: QRectF) -> None:
        paint_orb(p, rect.center(), 7.5, self._tm.theme.color("accent"))


class BatteryIndicator(BarButton):
    ICON_W = 25

    def __init__(self, tm: ThemeManager, parent=None):
        super().__init__(tm, "", interactive=False, pad=8, parent=parent)
        self._percent = 100
        self._plugged = False

    def set_state(self, percent: int, plugged: bool) -> None:
        self._percent, self._plugged = percent, plugged
        self.setText(f"{percent}%")
        self.update()

    def content_width(self) -> int:
        return super().content_width() + 6 + self.ICON_W

    def paint_content(self, p: QPainter, rect: QRectF) -> None:
        theme = self._tm.theme
        p.setFont(self._font())
        text_w = QFontMetrics(p.font()).horizontalAdvance(self._text)
        x = rect.left() + (rect.width() - (text_w + 6 + self.ICON_W)) / 2
        cy = rect.top() + rect.height() / 2

        p.setPen(theme.color("bar_text"))
        p.drawText(QRectF(x, rect.top(), text_w + 2, rect.height()),
                   Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft, self._text)

        ix = x + text_w + 6
        outline = theme.color("bar_text_secondary")
        p.setPen(QPen(outline, 1))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawRoundedRect(QRectF(ix + 0.5, cy - 5.5, 21, 11), 3, 3)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(outline)
        p.drawRoundedRect(QRectF(ix + 22.5, cy - 2.5, 2, 5), 1, 1)

        frac = max(0.0, min(1.0, self._percent / 100))
        if self._plugged:
            fill = theme.color("good")
        elif self._percent <= 15:
            fill = theme.color("danger")
        else:
            fill = theme.color("bar_text")
        p.setBrush(fill)
        p.drawRoundedRect(QRectF(ix + 2, cy - 4, 18 * frac, 8), 1.8, 1.8)


class StyledMenu(QMenu):
    """Rounded, theme-aware popup menu."""

    def __init__(self, tm: ThemeManager, parent=None):
        super().__init__(parent)
        self._tm = tm
        self.setWindowFlags(self.windowFlags()
                            | Qt.WindowType.FramelessWindowHint
                            | Qt.WindowType.NoDropShadowWindowHint)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.apply_theme()
        tm.changed.connect(self.apply_theme)

    def apply_theme(self) -> None:
        t = self._tm.theme
        radius = t.metric("menu_radius", 10)
        self.setFont(self._tm.font())
        self.setStyleSheet(f"""
            QMenu {{
                background-color: {t.rgba('menu_bg')};
                border: 1px solid {t.rgba('menu_border')};
                border-radius: {radius}px;
                padding: 5px;
            }}
            QMenu::item {{
                color: {t.rgba('menu_text')};
                padding: 5px 24px 5px 14px;
                border-radius: 5px;
                margin: 0px;
            }}
            QMenu::item:selected {{
                background-color: {t.rgba('menu_hover')};
                color: white;
            }}
            QMenu::item:disabled {{
                color: {t.rgba('text_secondary')};
                background: transparent;
            }}
            QMenu::separator {{
                height: 1px;
                background: {t.rgba('menu_separator')};
                margin: 5px 8px;
            }}
        """)
