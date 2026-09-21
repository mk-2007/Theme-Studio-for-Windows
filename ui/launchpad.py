"""Launchpad / Show Applications: a frosted-glass, paged app grid."""
from __future__ import annotations

import math
import time

from PyQt6.QtCore import QEvent, QPointF, QRectF, Qt, QTimer, pyqtSignal
from PyQt6.QtGui import (QColor, QFontMetrics, QLinearGradient, QPainter, QPen, QRadialGradient)
from PyQt6.QtWidgets import QLineEdit, QVBoxLayout, QWidget

from core import winapi
from core.index import AppEntry, AppIndex, launch_target
from core.settings import Settings
from core.theme import ThemeManager
from .glyphs import draw_search
from .icons import IconCache


class SearchField(QLineEdit):
    """Glass search pill with a magnifier."""
    escape = pyqtSignal()
    accept = pyqtSignal()
    page_left = pyqtSignal()
    page_right = pyqtSignal()

    def __init__(self, tm: ThemeManager, parent=None) -> None:
        super().__init__(parent)
        self._tm = tm
        self.setFrame(False)
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setTextMargins(26, 0, 10, 0)

    def keyPressEvent(self, e) -> None:
        key = e.key()
        if key == Qt.Key.Key_Escape:
            self.escape.emit()
        elif key in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            self.accept.emit()
        elif key == Qt.Key.Key_Left and not self.text():
            self.page_left.emit()
        elif key == Qt.Key.Key_Right and not self.text():
            self.page_right.emit()
        else:
            super().keyPressEvent(e)

    def paintEvent(self, e) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        t = self._tm.theme
        dark = t.mode == "dark"
        r = QRectF(self.rect()).adjusted(1, 1, -1, -1)
        radius = r.height() / 2
        p.setPen(QPen(QColor(255, 255, 255, 60 if dark else 170), 1))
        p.setBrush(t.color("field_bg"))
        p.drawRoundedRect(r, radius, radius)
        gloss = QLinearGradient(r.topLeft(), r.bottomLeft())
        gloss.setColorAt(0, QColor(255, 255, 255, 46 if dark else 110))
        gloss.setColorAt(0.5, QColor(255, 255, 255, 0))
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(gloss)
        p.drawRoundedRect(r, radius, radius)
        draw_search(p, QRectF(16, (self.height() - 18) / 2, 18, 18), t.color("text_secondary"))
        p.end()
        super().paintEvent(e)


class PageGrid(QWidget):
    launched = pyqtSignal(object)
    background_clicked = pyqtSignal()
    closed = pyqtSignal()

    def __init__(self, tm: ThemeManager, icons: IconCache, settings: Settings) -> None:
        super().__init__()
        self._tm, self._icons, self._settings = tm, icons, settings
        self._entries: list[AppEntry] = []
        self._page = 0
        self._page_pos = 0.0
        self._hover = -1
        self._pressed = -1
        self._press_x: float | None = None
        self._drag_dx = 0.0
        self._dragging = False
        self._dot_rects: list[QRectF] = []
        self._last_wheel = 0.0
        self._open_t = 1.0
        self._open_target = 1.0
        self._timer = QTimer(self, interval=16, timeout=self._tick)
        self.setMouseTracking(True)

    # ------------------------------------------------------------ data
    def set_entries(self, entries: list[AppEntry]) -> None:
        self._entries = entries
        self._page, self._page_pos = 0, 0.0
        self._hover = -1
        self.update()

    def _gnome(self) -> bool:
        return self._settings.get("menubar_layout", "macos") == "gnome"

    # ------------------------------------------------------------ metrics
    def _area(self) -> QRectF:
        w, h = self.width(), self.height()
        bottom = 30 if self._gnome() else 62
        right = 56 if self._gnome() else 0
        return QRectF(w * 0.08, 6, w * 0.84 - right, h - 6 - bottom)

    def _grid(self) -> tuple[int, int]:
        a = self._area()
        return max(3, min(8, int(a.width() // 172))), max(2, min(5, int(a.height() // 168)))

    def _per_page(self) -> int:
        cols, rows = self._grid()
        return cols * rows

    def _pages(self) -> int:
        return max(1, math.ceil(len(self._entries) / self._per_page()))

    # ------------------------------------------------------------ animation
    def open_animation(self) -> None:
        self._open_t, self._open_target = 0.0, 1.0
        self._timer.start()

    def close_animation(self) -> None:
        self._open_target = 0.0
        self._timer.start()

    def go(self, delta: int) -> None:
        self._page = min(max(self._page + delta, 0), self._pages() - 1)
        self._timer.start()

    def _tick(self) -> None:
        self._page_pos += (self._page - self._page_pos) * 0.22
        if abs(self._page_pos - self._page) < 0.003:
            self._page_pos = float(self._page)
        self._open_t += (self._open_target - self._open_t) * 0.24
        if abs(self._open_t - self._open_target) < 0.01:
            self._open_t = self._open_target
        self.update()
        if self._open_target == 0.0 and self._open_t <= 0.02:
            self._timer.stop()
            self.closed.emit()
        elif self._page_pos == self._page and self._open_t == self._open_target:
            self._timer.stop()

    # ------------------------------------------------------------ painting
    def paintEvent(self, _e) -> None:
        if not self._entries:
            self._paint_empty()
            return
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        p.setRenderHint(QPainter.RenderHint.TextAntialiasing)
        openness = self._open_t
        center = QPointF(self.width() / 2, self.height() / 2)
        zoom = 1.07 - 0.07 * openness
        p.translate(center)
        p.scale(zoom, zoom)
        p.translate(-center)

        area = self._area()
        cols, rows = self._grid()
        per = cols * rows
        tile_w, tile_h = area.width() / cols, area.height() / rows
        icon = min(tile_w * 0.56, tile_h * 0.55, 112)
        pos = self._page_pos - self._drag_dx / max(1, self.width())
        pages = self._pages()
        for page in (math.floor(pos), math.floor(pos) + 1):
            if page < 0 or page >= pages:
                continue
            base_x = (page - pos) * self.width()
            for k in range(per):
                idx = page * per + k
                if idx >= len(self._entries):
                    break
                cell = QRectF(area.x() + (k % cols) * tile_w + base_x, area.y() + (k // cols) * tile_h,
                              tile_w, tile_h)
                if cell.right() < 0 or cell.left() > self.width():
                    continue
                self._paint_tile(p, idx, cell, icon, openness)
        self._paint_dots(p, pages, openness)

    def _paint_empty(self) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.TextAntialiasing)
        p.setFont(self._tm.font(16))
        p.setPen(self._tm.theme.color("text_secondary"))
        p.drawText(QRectF(self.rect()), Qt.AlignmentFlag.AlignCenter, "No apps found")

    def _paint_tile(self, p: QPainter, idx: int, cell: QRectF, icon: float, openness: float) -> None:
        t = self._tm.theme
        dark = t.mode == "dark"
        entry = self._entries[idx]
        hovered = idx == self._hover and abs(self._page_pos - self._page) < 0.02 and not self._dragging
        pressed = idx == self._pressed and hovered
        inset = cell.adjusted(10, 6, -10, -6)
        radius = t.metric("widget_radius", 20) + 2
        p.setOpacity(openness)
        if hovered:
            p.setPen(QPen(QColor(255, 255, 255, 60 if dark else 150), 1))
            p.setBrush(QColor(255, 255, 255, 24 if dark else 80))
            p.drawRoundedRect(inset, radius, radius)
            gloss = QLinearGradient(inset.topLeft(), inset.bottomLeft())
            gloss.setColorAt(0, QColor(255, 255, 255, 52 if dark else 120))
            gloss.setColorAt(0.55, QColor(255, 255, 255, 0))
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(gloss)
            p.drawRoundedRect(inset, radius, radius)

        scale = 0.94 if pressed else (1.05 if hovered else 1.0)
        size = icon * scale
        top = inset.top() + (inset.height() - icon - 34) / 2
        rect = QRectF(cell.center().x() - size / 2, top + (icon - size) / 2, size, size)
        pm = self._icons.get(entry.icon_path, entry.name)
        shadow = self._icons.shadow(pm)
        p.setOpacity(openness * 0.7)
        p.drawPixmap(rect.translated(0, size * 0.07).adjusted(-size * 0.02, 0, size * 0.02, size * 0.03),
                     shadow, QRectF(shadow.rect()))
        p.setOpacity(openness)
        p.drawPixmap(rect, pm, QRectF(pm.rect()))

        font = self._tm.font(13, True)
        fm = QFontMetrics(font)
        label = fm.elidedText(entry.name, Qt.TextElideMode.ElideRight, int(cell.width() - 24))
        text_rect = QRectF(cell.left() + 8, top + icon + 10, cell.width() - 16, 22)
        p.setFont(font)
        if dark:
            p.setPen(QColor(0, 0, 0, 150))
            p.drawText(text_rect.translated(0, 1), Qt.AlignmentFlag.AlignCenter, label)
        p.setPen(t.color("text"))
        p.drawText(text_rect, Qt.AlignmentFlag.AlignCenter, label)
        p.setOpacity(1.0)

    def _paint_dots(self, p: QPainter, pages: int, openness: float) -> None:
        self._dot_rects = []
        if pages <= 1:
            return
        t = self._tm.theme
        vertical = self._gnome()
        step = 20
        total = (pages - 1) * step
        p.setPen(Qt.PenStyle.NoPen)
        for i in range(pages):
            if vertical:
                c = QPointF(self.width() - 26, self.height() / 2 - total / 2 + i * step)
            else:
                c = QPointF(self.width() / 2 - total / 2 + i * step, self.height() - 30)
            active = 1 - min(1.0, abs(i - self._page_pos))
            col = QColor(t.color("text"))
            col.setAlpha(int((80 + 160 * active) * openness))
            p.setBrush(col)
            p.drawEllipse(c, 4.2 + 1.2 * active, 4.2 + 1.2 * active)
            self._dot_rects.append(QRectF(c.x() - 12, c.y() - 12, 24, 24))

    # ------------------------------------------------------------ input
    def _tile_at(self, pos: QPointF) -> int:
        if abs(self._page_pos - self._page) > 0.02 or not self._entries:
            return -1
        area = self._area()
        cols, rows = self._grid()
        tile_w, tile_h = area.width() / cols, area.height() / rows
        x, y = pos.x() - area.x(), pos.y() - area.y()
        if x < 0 or y < 0 or x >= cols * tile_w or y >= rows * tile_h:
            return -1
        idx = self._page * cols * rows + int(y // tile_h) * cols + int(x // tile_w)
        return idx if idx < len(self._entries) else -1

    def wheelEvent(self, e) -> None:
        now = time.monotonic()
        if now - self._last_wheel < 0.22:
            return
        delta = e.angleDelta().y() or e.angleDelta().x()
        if delta:
            self._last_wheel = now
            self.go(-1 if delta > 0 else 1)

    def mousePressEvent(self, e) -> None:
        self._press_x = e.position().x()
        self._pressed = self._tile_at(e.position())
        self._dragging = False
        self._drag_dx = 0.0
        self.update()

    def mouseMoveEvent(self, e) -> None:
        if self._press_x is not None and e.buttons() & Qt.MouseButton.LeftButton:
            dx = e.position().x() - self._press_x
            if self._dragging or abs(dx) > 10:
                self._dragging = True
                at_start, at_end = self._page == 0 and dx > 0, self._page == self._pages() - 1 and dx < 0
                self._drag_dx = dx * (0.35 if at_start or at_end else 1.0)
                self.update()
            return
        idx = self._tile_at(e.position())
        if idx != self._hover:
            self._hover = idx
            self.update()

    def leaveEvent(self, _e) -> None:
        self._hover = -1
        self.update()

    def mouseReleaseEvent(self, e) -> None:
        pressed, self._pressed = self._pressed, -1
        if self._dragging:
            width = max(1, self.width())
            self._page_pos -= self._drag_dx / width           # continue from where the finger was
            if self._drag_dx < -width * 0.12:
                self.go(1)
            elif self._drag_dx > width * 0.12:
                self.go(-1)
            else:
                self.go(0)
            self._drag_dx, self._dragging, self._press_x = 0.0, False, None
            return
        self._press_x = None
        for i, rect in enumerate(self._dot_rects):
            if rect.contains(e.position()):
                self._page = i
                self._timer.start()
                return
        idx = self._tile_at(e.position())
        if idx >= 0 and idx == pressed:
            self.launched.emit(self._entries[idx])
        elif idx < 0:
            self.background_clicked.emit()
        self.update()


class Launchpad(QWidget):
    def __init__(self, tm: ThemeManager, index: AppIndex, icons: IconCache, settings: Settings) -> None:
        super().__init__(None, Qt.WindowType.Tool | Qt.WindowType.FramelessWindowHint
                         | Qt.WindowType.WindowStaysOnTopHint)
        self._tm, self._index, self._settings = tm, index, settings
        self._blur_ok = False
        self._closing = False
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setWindowTitle("Theme Studio Launchpad")

        self.search = SearchField(tm, self)
        self.search.setPlaceholderText("Search")
        self.search.setFixedSize(330, 40)
        self.search.textChanged.connect(self._refilter)
        self.search.escape.connect(self.close_pad)
        self.search.accept.connect(self._launch_first)

        self.grid = PageGrid(tm, icons, settings)
        self.grid.launched.connect(self._launch)
        self.grid.background_clicked.connect(self.close_pad)
        self.grid.closed.connect(self._finish_close)
        self.search.page_left.connect(lambda: self.grid.go(-1))
        self.search.page_right.connect(lambda: self.grid.go(1))

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 46, 0, 0)
        layout.setSpacing(26)
        layout.addWidget(self.search, 0, Qt.AlignmentFlag.AlignHCenter)
        layout.addWidget(self.grid, 1)
        tm.changed.connect(self._style)
        index.apps_ready.connect(self._refilter)
        self._style()

    def _style(self) -> None:
        t = self._tm.theme
        self.search.setFont(self._tm.font(15))
        self.search.setStyleSheet(
            f"QLineEdit {{ background: transparent; border: none; color: {t.rgba('text')};"
            f" selection-background-color: {t.rgba('accent')};"
            f" placeholder-text-color: {t.rgba('text_secondary')}; }}")
        self.update()

    # ---------------------------------------------------------------- open / close
    def open_pad(self) -> None:
        self._closing = False
        self.setGeometry(self.screen().geometry())
        self.search.clear()
        self._refilter()
        self.show()
        if winapi.IS_WINDOWS:
            hwnd = int(self.winId())
            winapi.prepare_bar_window(hwnd, noactivate=False)
            tint = self._tm.theme.color("blur_tint")
            self._blur_ok = winapi.enable_blur(hwnd, tint.red(), tint.green(), tint.blue(), 120)
            winapi.activate_window(hwnd)
        self.raise_()
        self.activateWindow()
        self.search.setFocus()
        self.grid.open_animation()

    def close_pad(self) -> None:
        if not self.isVisible() or self._closing:
            return
        self._closing = True
        self.grid.close_animation()

    def _finish_close(self) -> None:
        self.hide()
        self._closing = False

    def toggle(self) -> None:
        self.close_pad() if self.isVisible() else self.open_pad()

    def _refilter(self) -> None:
        self.grid.set_entries(self._index.search_apps(self.search.text()))

    def _launch(self, entry: AppEntry) -> None:
        launch_target(entry.launch)
        self.close_pad()

    def _launch_first(self) -> None:
        results = self._index.search_apps(self.search.text(), limit=1)
        if results:
            self._launch(results[0])

    # ---------------------------------------------------------------- background
    def paintEvent(self, _e) -> None:
        p = QPainter(self)
        t = self._tm.theme
        dark = t.mode == "dark"
        w, h = self.width(), self.height()
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        if self._blur_ok:
            p.fillRect(self.rect(), t.color("scrim"))
        else:  # no real blur available: a rich gradient instead
            g = QLinearGradient(0, 0, w, h)
            if dark:
                g.setColorAt(0, QColor(28, 32, 48, 246))
                g.setColorAt(1, QColor(12, 14, 24, 250))
            else:
                g.setColorAt(0, QColor(238, 241, 248, 246))
                g.setColorAt(1, QColor(214, 220, 236, 250))
            p.fillRect(self.rect(), g)
        vignette = QRadialGradient(QPointF(w / 2, h * 0.42), max(w, h) * 0.78)
        vignette.setColorAt(0.0, QColor(0, 0, 0, 0))
        vignette.setColorAt(0.62, QColor(0, 0, 0, 0))
        vignette.setColorAt(1.0, QColor(0, 0, 0, 120) if dark else QColor(255, 255, 255, 110))
        p.fillRect(self.rect(), vignette)
        sheen = QLinearGradient(0, 0, 0, h * 0.4)
        sheen.setColorAt(0, QColor(255, 255, 255, 30 if dark else 70))
        sheen.setColorAt(1, QColor(255, 255, 255, 0))
        p.fillRect(QRectF(0, 0, w, h * 0.4), sheen)

    def event(self, e) -> bool:
        if e.type() == QEvent.Type.WindowDeactivate and self.isVisible() and winapi.IS_WINDOWS:
            QTimer.singleShot(150, lambda: self.close_pad() if not self.isActiveWindow() else None)
        return super().event(e)
