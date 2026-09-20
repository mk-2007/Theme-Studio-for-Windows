"""Launchpad: full-screen blurred grid of every installed app, with search."""
from __future__ import annotations

from PyQt6.QtCore import QEvent, QPointF, QRectF, Qt, QTimer, pyqtSignal
from PyQt6.QtGui import QColor, QFontMetrics, QPainter
from PyQt6.QtWidgets import QLineEdit, QVBoxLayout, QWidget

from core import winapi
from core.index import AppEntry, AppIndex, launch_target
from core.theme import ThemeManager
from .icons import IconCache

TILE_W, TILE_H, ICON = 132, 138, 76


class SearchField(QLineEdit):
    escape = pyqtSignal()
    accept = pyqtSignal()

    def keyPressEvent(self, e) -> None:
        if e.key() == Qt.Key.Key_Escape:
            self.escape.emit()
        elif e.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            self.accept.emit()
        else:
            super().keyPressEvent(e)


class AppGrid(QWidget):
    launched = pyqtSignal(object)
    background_clicked = pyqtSignal()

    def __init__(self, tm: ThemeManager, icons: IconCache) -> None:
        super().__init__()
        self._tm = tm
        self._icons = icons
        self._entries: list[AppEntry] = []
        self._scroll = 0.0
        self._hover = -1
        self._pressed = -1
        self.setMouseTracking(True)

    def set_entries(self, entries: list[AppEntry]) -> None:
        self._entries = entries
        self._scroll = 0.0
        self._hover = -1
        self.update()

    # layout
    def _cols(self) -> int:
        return max(3, self.width() // TILE_W)

    def _origin_x(self) -> float:
        return (self.width() - self._cols() * TILE_W) / 2

    def _content_height(self) -> float:
        rows = -(-len(self._entries) // self._cols())
        return rows * TILE_H + 40

    def _max_scroll(self) -> float:
        return max(0.0, self._content_height() - self.height())

    def _index_at(self, pos: QPointF) -> int:
        x = pos.x() - self._origin_x()
        y = pos.y() + self._scroll
        if x < 0 or y < 0:
            return -1
        col, row = int(x // TILE_W), int(y // TILE_H)
        if col >= self._cols():
            return -1
        idx = row * self._cols() + col
        return idx if 0 <= idx < len(self._entries) else -1

    # painting
    def paintEvent(self, _event) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        p.setRenderHint(QPainter.RenderHint.TextAntialiasing)
        t = self._tm.theme
        cols, ox = self._cols(), self._origin_x()
        first_row = int(self._scroll // TILE_H)
        last_row = int((self._scroll + self.height()) // TILE_H) + 1
        font = self._tm.font(13)
        fm = QFontMetrics(font)
        for row in range(first_row, last_row + 1):
            for col in range(cols):
                idx = row * cols + col
                if idx >= len(self._entries):
                    break
                entry = self._entries[idx]
                x, y = ox + col * TILE_W, row * TILE_H - self._scroll
                if idx == self._hover:
                    p.setPen(Qt.PenStyle.NoPen)
                    p.setBrush(t.color("hover"))
                    p.drawRoundedRect(QRectF(x + 8, y + 4, TILE_W - 16, TILE_H - 8), 16, 16)
                pm = self._icons.get(entry.icon_path, entry.name, request=96)
                scale = 0.94 if idx == self._pressed else 1.0
                size = ICON * scale
                target = QRectF(x + (TILE_W - size) / 2, y + 14 + (ICON - size) / 2, size, size)
                p.drawPixmap(target, pm, QRectF(pm.rect()))
                p.setFont(font)
                p.setPen(t.color("text"))
                label = fm.elidedText(entry.name, Qt.TextElideMode.ElideRight, TILE_W - 20)
                p.drawText(QRectF(x + 6, y + ICON + 20, TILE_W - 12, 24), Qt.AlignmentFlag.AlignCenter, label)

    # input
    def wheelEvent(self, e) -> None:
        self._scroll = min(max(0.0, self._scroll - e.angleDelta().y() * 0.6), self._max_scroll())
        self.update()

    def mouseMoveEvent(self, e) -> None:
        idx = self._index_at(e.position())
        if idx != self._hover:
            self._hover = idx
            self.update()

    def leaveEvent(self, _e) -> None:
        self._hover = -1
        self.update()

    def mousePressEvent(self, e) -> None:
        self._pressed = self._index_at(e.position())
        self.update()

    def mouseReleaseEvent(self, e) -> None:
        idx = self._index_at(e.position())
        pressed, self._pressed = self._pressed, -1
        self.update()
        if idx < 0:
            self.background_clicked.emit()
        elif idx == pressed:
            self.launched.emit(self._entries[idx])


class Launchpad(QWidget):
    def __init__(self, tm: ThemeManager, index: AppIndex, icons: IconCache) -> None:
        super().__init__(None, Qt.WindowType.Tool | Qt.WindowType.FramelessWindowHint
                         | Qt.WindowType.WindowStaysOnTopHint)
        self._tm = tm
        self._index = index
        self._blur_ok = False
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setWindowTitle("Theme Studio Launchpad")

        self.search = SearchField(self)
        self.search.setPlaceholderText("Search")
        self.search.setFixedSize(320, 38)
        self.search.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.search.textChanged.connect(self._refilter)
        self.search.escape.connect(self.close_pad)
        self.search.accept.connect(self._launch_first)

        self.grid = AppGrid(tm, icons)
        self.grid.launched.connect(self._launch)
        self.grid.background_clicked.connect(self.close_pad)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 54, 0, 0)
        layout.setSpacing(30)
        layout.addWidget(self.search, 0, Qt.AlignmentFlag.AlignHCenter)
        layout.addWidget(self.grid, 1)
        tm.changed.connect(self._style)
        index.apps_ready.connect(self._refilter)
        self._style()

    def _style(self) -> None:
        t = self._tm.theme
        self.search.setFont(self._tm.font(15))
        self.search.setStyleSheet(
            f"QLineEdit {{ background: {t.rgba('field_bg')}; border: 1px solid {t.rgba('bar_border')};"
            f" border-radius: 12px; color: {t.rgba('text')}; padding: 0 12px;"
            f" placeholder-text-color: {t.rgba('text_secondary')}; }}")
        self.update()

    def open_pad(self) -> None:
        screen = self.screen()
        self.setGeometry(screen.geometry())
        self.search.clear()
        self._refilter()
        self.show()
        if winapi.IS_WINDOWS:
            hwnd = int(self.winId())
            winapi.prepare_bar_window(hwnd, noactivate=False)
            tint = self._tm.theme.color("blur_tint")
            self._blur_ok = winapi.enable_blur(hwnd, tint.red(), tint.green(), tint.blue(), 160)
            winapi.activate_window(hwnd)
        self.raise_()
        self.activateWindow()
        self.search.setFocus()

    def close_pad(self) -> None:
        self.hide()

    def toggle(self) -> None:
        self.close_pad() if self.isVisible() else self.open_pad()

    def _refilter(self) -> None:
        self.grid.set_entries(self._index.search_apps(self.search.text()))

    def _launch(self, entry: AppEntry) -> None:
        self.close_pad()
        launch_target(entry.launch)

    def _launch_first(self) -> None:
        results = self._index.search_apps(self.search.text(), limit=1)
        if results:
            self._launch(results[0])

    def paintEvent(self, _e) -> None:
        p = QPainter(self)
        p.fillRect(self.rect(), self._tm.theme.color("scrim") if self._blur_ok
                   else QColor(20, 22, 30, 235) if self._tm.theme.mode == "dark" else QColor(235, 238, 245, 240))

    def event(self, e) -> bool:
        if e.type() == QEvent.Type.WindowDeactivate and self.isVisible() and winapi.IS_WINDOWS:
            QTimer.singleShot(120, lambda: self.hide() if not self.isActiveWindow() else None)
        return super().event(e)
