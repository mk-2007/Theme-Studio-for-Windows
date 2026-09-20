"""Spotlight: Alt+Space search for apps, files, math, system commands and the web."""
from __future__ import annotations

import time
import urllib.parse
from dataclasses import dataclass
from typing import Callable

from PyQt6.QtCore import QEvent, QRectF, Qt, QTimer, pyqtSignal
from PyQt6.QtGui import QColor, QFontMetrics, QGuiApplication, QPainter, QPen
from PyQt6.QtWidgets import QLineEdit, QWidget

from core import calc, system, winapi
from core.index import AppIndex, launch_target
from core.theme import ThemeManager
from .glyphs import draw_search
from .icons import IconCache, glyph_pixmap

PANEL_W = 640
MARGIN = 24
FIELD_H = 64
ROW_H = 46
MAX_ROWS = 8


@dataclass
class Result:
    title: str
    subtitle: str
    kind: str                       # label shown at the right edge
    run: Callable[[], None]
    icon_path: str = ""
    glyph: str = ""
    hue: int = 210


class QueryField(QLineEdit):
    up = pyqtSignal()
    down = pyqtSignal()
    escape = pyqtSignal()
    accept = pyqtSignal()

    def keyPressEvent(self, e) -> None:
        key = e.key()
        if key == Qt.Key.Key_Escape:
            self.escape.emit()
        elif key == Qt.Key.Key_Up:
            self.up.emit()
        elif key == Qt.Key.Key_Down:
            self.down.emit()
        elif key in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            self.accept.emit()
        else:
            super().keyPressEvent(e)


class Spotlight(QWidget):
    def __init__(self, tm: ThemeManager, index: AppIndex, icons: IconCache, commands: dict) -> None:
        """`commands` maps a keyword to (title, callable) for the built-in quick actions."""
        super().__init__(None, Qt.WindowType.Tool | Qt.WindowType.FramelessWindowHint
                         | Qt.WindowType.WindowStaysOnTopHint)
        self._tm = tm
        self._index = index
        self._icons = icons
        self._commands = commands
        self._results: list[Result] = []
        self._selected = 0
        self._hover = -1
        self._shown_at = 0.0
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setWindowTitle("Theme Studio Spotlight")

        self.field = QueryField(self)
        self.field.setPlaceholderText("Spotlight Search")
        self.field.setFrame(False)
        self.field.textChanged.connect(self._search)
        self.field.up.connect(lambda: self._move(-1))
        self.field.down.connect(lambda: self._move(1))
        self.field.escape.connect(self.hide)
        self.field.accept.connect(self._run_selected)
        self.setMouseTracking(True)
        tm.changed.connect(self._style)
        self._style()
        self._resize_for(0)

    def _style(self) -> None:
        t = self._tm.theme
        self.field.setFont(self._tm.font(22))
        self.field.setStyleSheet(
            f"QLineEdit {{ background: transparent; color: {t.rgba('text')}; border: none;"
            f" selection-background-color: {t.rgba('accent')}; placeholder-text-color: {t.rgba('text_secondary')}; }}")
        self.update()

    # ------------------------------------------------------------------ show / hide
    def open_bar(self) -> None:
        self.field.clear()
        self._search("")
        screen = QGuiApplication.primaryScreen().geometry()
        self.move(screen.center().x() - self.width() // 2, screen.y() + int(screen.height() * 0.17))
        self._shown_at = time.monotonic()
        self.show()
        if winapi.IS_WINDOWS:
            hwnd = int(self.winId())
            winapi.prepare_bar_window(hwnd, noactivate=False)
            winapi.activate_window(hwnd)
        self.raise_()
        self.activateWindow()
        self.field.setFocus()

    def toggle(self) -> None:
        self.hide() if self.isVisible() else self.open_bar()

    def event(self, e) -> bool:
        if e.type() == QEvent.Type.WindowDeactivate and self.isVisible() and winapi.IS_WINDOWS:
            if time.monotonic() - self._shown_at > 0.4:
                QTimer.singleShot(80, lambda: self.hide() if not self.isActiveWindow() else None)
        return super().event(e)

    # ------------------------------------------------------------------ searching
    def _search(self, text: str) -> None:
        q = text.strip()
        results: list[Result] = []
        if q:
            value = calc.evaluate(q)
            if value is not None:
                results.append(Result(f"= {value}", f"{q}  \u2022  Enter to copy", "Calculator",
                                      lambda v=value: QGuiApplication.clipboard().setText(v.replace(",", "")),
                                      glyph="=", hue=25))
            lowered = q.lower()
            for keyword, (title, action) in self._commands.items():
                if len(lowered) >= 2 and (keyword.startswith(lowered) or lowered in keyword):
                    results.append(Result(title, "System command", "Command", action, glyph="\u2318", hue=265))
            for app in self._index.search_apps(q, limit=6):
                results.append(Result(app.name, "Application", "App",
                                      lambda a=app: launch_target(a.launch), icon_path=app.icon_path))
            for f in self._index.search_files(q, limit=4):
                results.append(Result(f.name, f.path, "File", lambda path=f.path: launch_target(path),
                                      icon_path=f.path))
            url = "https://www.google.com/search?q=" + urllib.parse.quote_plus(q)
            results.append(Result(f"Search the web for \u201c{q}\u201d", "Open in your browser", "Web",
                                  lambda u=url: system.open_uri(u), glyph="\U0001F50D", hue=205))
        self._results = results[:MAX_ROWS]
        self._selected = 0
        self._hover = -1
        self._resize_for(len(self._results))
        self.update()

    def _resize_for(self, rows: int) -> None:
        body = rows * ROW_H + 14 if rows else 0
        self.setFixedSize(PANEL_W + 2 * MARGIN, FIELD_H + body + 2 * MARGIN)
        self.field.setGeometry(MARGIN + 54, MARGIN + 8, PANEL_W - 54 - 20, FIELD_H - 16)

    def _move(self, delta: int) -> None:
        if self._results:
            self._selected = (self._selected + delta) % len(self._results)
            self.update()

    def _run_selected(self) -> None:
        if not self._results:
            return
        result = self._results[self._selected]
        self.hide()
        result.run()

    # ------------------------------------------------------------------ painting
    def _row_rect(self, i: int) -> QRectF:
        return QRectF(MARGIN + 8, MARGIN + FIELD_H + 4 + i * ROW_H, PANEL_W - 16, ROW_H - 2)

    def paintEvent(self, _e) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        p.setRenderHint(QPainter.RenderHint.TextAntialiasing)
        t = self._tm.theme
        panel = QRectF(MARGIN, MARGIN, PANEL_W, self.height() - 2 * MARGIN)
        for i in range(1, 9):   # soft shadow
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QColor(0, 0, 0, 7))
            p.drawRoundedRect(panel.adjusted(-i * 2, -i * 2 + 6, i * 2, i * 2 + 6), 20 + i * 2, 20 + i * 2)
        p.setBrush(t.color("panel_bg"))
        p.setPen(QPen(t.color("menu_border"), 1))
        p.drawRoundedRect(panel, 20, 20)
        draw_search(p, QRectF(MARGIN + 18, MARGIN + 16, 32, 32), t.color("text_secondary"))

        if not self._results:
            return
        p.setPen(QPen(t.color("menu_separator"), 1))
        y = MARGIN + FIELD_H
        p.drawLine(MARGIN + 16, y, MARGIN + PANEL_W - 16, y)
        small = self._tm.font(12)
        for i, res in enumerate(self._results):
            row = self._row_rect(i)
            selected = i == self._selected
            if selected or i == self._hover:
                p.setPen(Qt.PenStyle.NoPen)
                p.setBrush(t.color("menu_hover") if selected else t.color("hover"))
                p.drawRoundedRect(row, 10, 10)
            if res.glyph:
                pm = glyph_pixmap(res.glyph, res.hue)
            else:
                pm = self._icons.get(res.icon_path, res.title, request=64)
            p.drawPixmap(QRectF(row.left() + 10, row.top() + 6, 30, 30), pm, QRectF(pm.rect()))
            fg = QColor(255, 255, 255) if selected else t.color("text")
            sub = QColor(255, 255, 255, 190) if selected else t.color("text_secondary")
            title_font = self._tm.font(15)
            p.setFont(title_font)
            p.setPen(fg)
            has_sub = res.kind in ("File", "Calculator")
            top = row.top() + (2 if has_sub else 0)
            height = 22 if has_sub else row.height()
            elided = QFontMetrics(title_font).elidedText(res.title, Qt.TextElideMode.ElideMiddle, 400)
            p.drawText(QRectF(row.left() + 52, top, 420, height),
                       Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft, elided)
            if has_sub:
                p.setFont(small)
                p.setPen(sub)
                sub_text = QFontMetrics(small).elidedText(res.subtitle, Qt.TextElideMode.ElideMiddle, 420)
                p.drawText(QRectF(row.left() + 52, row.top() + 22, 420, 18),
                           Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft, sub_text)
            p.setFont(small)
            p.setPen(sub)
            p.drawText(QRectF(row.right() - 110, row.top(), 98, row.height()),
                       Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignRight, res.kind)

    # ------------------------------------------------------------------ mouse
    def _row_at(self, pos) -> int:
        for i in range(len(self._results)):
            if self._row_rect(i).contains(pos):
                return i
        return -1

    def mouseMoveEvent(self, e) -> None:
        idx = self._row_at(e.position())
        if idx != self._hover:
            self._hover = idx
            self.update()

    def mouseReleaseEvent(self, e) -> None:
        idx = self._row_at(e.position())
        if idx >= 0:
            self._selected = idx
            self._run_selected()
