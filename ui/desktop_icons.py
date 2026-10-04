"""Desktop icons drawn by Theme Studio (macOS/GNOME style), replacing the native icon layer."""
from __future__ import annotations

import os
import subprocess
from dataclasses import dataclass
from pathlib import Path

from PyQt6.QtCore import QFileSystemWatcher, QPointF, QRectF, QStandardPaths, Qt, QTimer
from PyQt6.QtGui import QColor, QFontMetrics, QGuiApplication, QPainter
from PyQt6.QtWidgets import QWidget

from core import syspath, winapi
from core.index import launch_target
from core.settings import Settings
from core.theme import ThemeManager
from .icons import IconCache
from .widgets import StyledMenu

CELL_W, CELL_H, ICON, MARGIN = 96, 104, 54, 16
_SKIP = {"desktop.ini", "thumbs.db"}


@dataclass
class DesktopItem:
    name: str            # display name
    file: str            # file name on disk (settings key)
    path: str
    col: int = 0
    row: int = 0
    px: float = 0.0      # current pixel position (top-left of the cell)
    py: float = 0.0


def _wrap(text: str, fm: QFontMetrics, width: int) -> list[str]:
    """Greedy word wrap into at most two lines; long words are broken, overflow is middle-elided."""
    lines: list[str] = []
    cur = ""
    for word in text.split(" "):
        trial = f"{cur} {word}".strip()
        if fm.horizontalAdvance(trial) <= width:
            cur = trial
            continue
        if cur:
            lines.append(cur)
            cur = ""
        while fm.horizontalAdvance(word) > width and len(word) > 1:
            k = len(word)
            while k > 1 and fm.horizontalAdvance(word[:k]) > width:
                k -= 1
            lines.append(word[:k])
            word = word[k:]
        cur = word
    if cur:
        lines.append(cur)
    if len(lines) > 2:
        lines = [lines[0], fm.elidedText(" ".join(lines[1:]), Qt.TextElideMode.ElideMiddle, width)]
    return lines


class DesktopIcons(QWidget):
    def __init__(self, tm: ThemeManager, icons: IconCache, settings: Settings) -> None:
        super().__init__(None, Qt.WindowType.Tool | Qt.WindowType.FramelessWindowHint)
        self._tm, self._icons, self._settings = tm, icons, settings
        self._items: list[DesktopItem] = []
        self._selected = -1
        self._drag: tuple[int, QPointF] | None = None
        self._active = False
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
        self.setWindowTitle("Theme Studio Desktop")
        self._watcher = QFileSystemWatcher(self)
        self._watcher.directoryChanged.connect(lambda _p: self._reload_timer.start())
        self._reload_timer = QTimer(self, singleShot=True, interval=350, timeout=self.reload)
        self._bottom_timer = QTimer(self, interval=2500, timeout=self._push_bottom)
        tm.changed.connect(self.update)

    # ------------------------------------------------------------ lifecycle
    def desktop_dirs(self) -> list[str]:
        dirs = [QStandardPaths.writableLocation(QStandardPaths.StandardLocation.DesktopLocation)
                or str(Path.home() / "Desktop")]
        public = os.environ.get("PUBLIC")
        if public:
            dirs.append(os.path.join(public, "Desktop"))
        return [d for d in dirs if d and os.path.isdir(d)]

    def enabled(self) -> bool:
        return bool(self._settings.get("desktop_icons", True))

    def start(self) -> None:
        if not self.enabled():
            return
        self._active = True
        self.setGeometry(self.screen().geometry())
        self.show()
        if winapi.IS_WINDOWS:
            winapi.prepare_bar_window(int(self.winId()))
            winapi.set_window_z(int(self.winId()), "bottom")
            winapi.set_desktop_icons_visible(False)
        for d in self.desktop_dirs():
            self._watcher.addPath(d)
        self.reload()
        self._bottom_timer.start()

    def stop(self) -> None:
        self._bottom_timer.stop()
        if self._active and winapi.IS_WINDOWS:
            winapi.set_desktop_icons_visible(True)
        self._active = False
        self.hide()

    def refresh_enabled(self) -> None:
        if self.enabled() and not self._active:
            self.start()
        elif not self.enabled() and self._active:
            self.stop()

    def _push_bottom(self) -> None:
        if winapi.IS_WINDOWS and self.isVisible():
            winapi.set_window_z(int(self.winId()), "bottom")

    # ------------------------------------------------------------ layout
    def _top(self) -> int:
        return self._tm.theme.metric("bar_height", 26) + 12

    def _rows(self) -> int:
        return max(1, (self.height() - self._top() - 16) // CELL_H)

    def _cols(self) -> int:
        return max(1, (self.width() - 2 * MARGIN) // CELL_W)

    def _cell_pos(self, col: int, row: int) -> tuple[float, float]:
        return self.width() - MARGIN - (col + 1) * CELL_W, self._top() + row * CELL_H

    def reload(self) -> None:
        found: list[DesktopItem] = []
        seen: set[str] = set()
        for folder in self.desktop_dirs():
            try:
                entries = sorted(os.scandir(folder), key=lambda e: (not e.is_dir(), e.name.lower()))
            except OSError:
                continue
            for e in entries:
                low = e.name.lower()
                if low in _SKIP or e.name.startswith(".") or low in seen:
                    continue
                seen.add(low)
                display = e.name[:-4] if low.endswith((".lnk", ".url")) else e.name
                found.append(DesktopItem(display, e.name, e.path))
        saved: dict = self._settings.get("desktop_icon_cells", {}) or {}
        rows, cols = self._rows(), self._cols()
        taken: set[tuple[int, int]] = set()
        unplaced = []
        for item in found:
            cell = saved.get(item.file)
            if cell and 0 <= cell[0] < cols and 0 <= cell[1] < rows and tuple(cell) not in taken:
                item.col, item.row = cell
                taken.add((item.col, item.row))
            else:
                unplaced.append(item)
        free = ((c, r) for c in range(cols) for r in range(rows) if (c, r) not in taken)
        for item in unplaced:
            item.col, item.row = next(free, (0, 0))
        for item in found:
            item.px, item.py = self._cell_pos(item.col, item.row)
        self._items = found
        self._selected = -1
        self.update()

    def _save(self) -> None:
        self._settings.set("desktop_icon_cells", {i.file: [i.col, i.row] for i in self._items})

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        if self._items:
            self.reload()

    # ------------------------------------------------------------ painting
    def paintEvent(self, _e) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        p.setRenderHint(QPainter.RenderHint.TextAntialiasing)
        t = self._tm.theme
        font = self._tm.font(12)
        fm = QFontMetrics(font)
        for i, item in enumerate(self._items):
            x, y = item.px, item.py
            icon = QRectF(x + (CELL_W - ICON) / 2, y + 6, ICON, ICON)
            selected = i == self._selected
            if selected:
                p.setPen(Qt.PenStyle.NoPen)
                p.setBrush(QColor(255, 255, 255, 60))
                p.drawRoundedRect(icon.adjusted(-7, -6, 7, 6), 12, 12)
            if self._drag and self._drag[0] == i:
                p.setOpacity(0.75)
            pm = self._icons.get(item.path, item.name, request=128)
            p.drawPixmap(icon, pm, QRectF(pm.rect()))
            p.setOpacity(1.0)

            lines = _wrap(item.name, fm, CELL_W - 14)
            p.setFont(font)
            top = y + ICON + 12
            for n, line in enumerate(lines):
                line_w = fm.horizontalAdvance(line)
                line_rect = QRectF(x + (CELL_W - line_w) / 2, top + n * 15, line_w, 15)
                if selected:
                    p.setPen(Qt.PenStyle.NoPen)
                    p.setBrush(t.color("accent"))
                    p.drawRoundedRect(line_rect.adjusted(-5, -1, 5, 1), 6, 6)
                p.setPen(QColor(0, 0, 0, 170))
                p.drawText(line_rect.translated(0, 1), Qt.AlignmentFlag.AlignCenter, line)
                p.setPen(QColor(255, 255, 255))
                p.drawText(line_rect, Qt.AlignmentFlag.AlignCenter, line)

    # ------------------------------------------------------------ input
    def _hit(self, pos: QPointF) -> int:
        for i in range(len(self._items) - 1, -1, -1):
            it = self._items[i]
            if QRectF(it.px + 6, it.py + 2, CELL_W - 12, CELL_H - 8).contains(pos):
                return i
        return -1

    def mousePressEvent(self, e) -> None:
        idx = self._hit(e.position())
        self._selected = idx
        if idx >= 0 and e.button() == Qt.MouseButton.LeftButton:
            it = self._items[idx]
            self._drag = (idx, e.position() - QPointF(it.px, it.py))
        self.update()

    def mouseMoveEvent(self, e) -> None:
        if self._drag and e.buttons() & Qt.MouseButton.LeftButton:
            idx, offset = self._drag
            it = self._items[idx]
            it.px, it.py = e.position().x() - offset.x(), e.position().y() - offset.y()
            self.update()

    def mouseReleaseEvent(self, e) -> None:
        if self._drag:
            idx, _off = self._drag
            self._drag = None
            it = self._items[idx]
            col = round((self.width() - MARGIN - CELL_W - it.px) / CELL_W)
            row = round((it.py - self._top()) / CELL_H)
            col, row = min(max(col, 0), self._cols() - 1), min(max(row, 0), self._rows() - 1)
            if not any(o is not it and (o.col, o.row) == (col, row) for o in self._items):
                it.col, it.row = col, row
                self._save()
            it.px, it.py = self._cell_pos(it.col, it.row)
            self.update()

    def mouseDoubleClickEvent(self, e) -> None:
        idx = self._hit(e.position())
        if idx >= 0 and e.button() == Qt.MouseButton.LeftButton:
            launch_target(self._items[idx].path)

    def contextMenuEvent(self, e) -> None:
        idx = self._hit(QPointF(e.pos()))
        if idx < 0:
            return
        self._selected = idx
        item = self._items[idx]
        menu = StyledMenu(self._tm)
        menu.addAction("Open").triggered.connect(lambda: launch_target(item.path))
        if winapi.IS_WINDOWS:
            menu.addAction("Show in Explorer").triggered.connect(
                lambda: subprocess.Popen([syspath.tool("explorer"), f"/select,{item.path}"]))
        menu.addAction("Copy Path").triggered.connect(lambda: QGuiApplication.clipboard().setText(item.path))
        menu.addSeparator()
        menu.addAction("Refresh Desktop").triggered.connect(self.reload)
        menu.exec(e.globalPos())
        self.update()
