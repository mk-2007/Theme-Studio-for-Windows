"""Desktop widgets (clock, weather, system, calendar, notes) living on the desktop layer."""
from __future__ import annotations

import calendar
import math
import os
import threading
from datetime import date, datetime

import psutil
from PyQt6.QtCore import QObject, QPoint, QPointF, QRectF, Qt, QTimer, pyqtSignal
from PyQt6.QtGui import QColor, QFont, QFontMetrics, QLinearGradient, QPainter, QPen
from PyQt6.QtWidgets import QPlainTextEdit, QWidget

from core import weather, winapi
from core.settings import Settings
from core.theme import ThemeManager
from .widgets import StyledMenu

GRID = 8
EMOJI_FONTS = ["Segoe UI Emoji", "Apple Color Emoji", "Noto Color Emoji"]

SIZES = {
    "weather": (338, 158), "clock": (158, 158), "system": (158, 158),
    "calendar": (338, 262), "notes": (338, 200),
}
TITLES = {"weather": "Weather", "clock": "Clock", "system": "System", "calendar": "Calendar", "notes": "Notes"}
DEFAULT_VISIBLE = {"weather": True, "clock": True, "system": True, "calendar": True, "notes": False}


class DesktopWidget(QWidget):
    NO_ACTIVATE = True

    def __init__(self, wid: str, tm: ThemeManager, manager: "WidgetManager") -> None:
        super().__init__(None, Qt.WindowType.Tool | Qt.WindowType.FramelessWindowHint)
        self.wid = wid
        self._tm = tm
        self._manager = manager
        self._drag_offset: QPoint | None = None
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        if self.NO_ACTIVATE:
            self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
        self.setFixedSize(*SIZES[wid])
        self.setWindowTitle(f"Theme Studio {TITLES[wid]}")
        tm.changed.connect(self.update)

    def hwnd(self) -> int:
        return int(self.winId())

    # ---- painting -------------------------------------------------------------
    def paintEvent(self, _event) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setRenderHint(QPainter.RenderHint.TextAntialiasing)
        t = self._tm.theme
        radius = t.metric("widget_radius", 22)
        r = QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(t.color("widget_bg"))
        p.drawRoundedRect(r, radius, radius)
        glow = QLinearGradient(r.topLeft(), r.bottomLeft())
        glow.setColorAt(0, t.color("dock_highlight"))
        glow.setColorAt(0.5, QColor(255, 255, 255, 0))
        p.setBrush(glow)
        p.drawRoundedRect(r, radius, radius)
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.setPen(QPen(t.color("widget_border"), 1))
        p.drawRoundedRect(r, radius, radius)
        self.paint_body(p, QRectF(self.rect()))

    def paint_body(self, p: QPainter, r: QRectF) -> None:
        pass

    def text(self, p: QPainter, rect: QRectF, s: str, size: int, key: str = "text",
             bold: bool = False, align=Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter) -> None:
        p.setFont(self._tm.font(size, bold))
        p.setPen(self._tm.theme.color(key))
        p.drawText(rect, align, s)

    # ---- dragging -------------------------------------------------------------
    def mousePressEvent(self, e) -> None:
        if e.button() == Qt.MouseButton.LeftButton:
            self._drag_offset = e.globalPosition().toPoint() - self.pos()

    def mouseMoveEvent(self, e) -> None:
        if self._drag_offset is not None and e.buttons() & Qt.MouseButton.LeftButton:
            self.move(e.globalPosition().toPoint() - self._drag_offset)

    def mouseReleaseEvent(self, e) -> None:
        if self._drag_offset is not None:
            self._drag_offset = None
            self.move(round(self.x() / GRID) * GRID, round(self.y() / GRID) * GRID)
            self._manager.save_positions()

    def contextMenuEvent(self, e) -> None:
        self._manager.show_menu(self, e.globalPos())


# ============================================================================ Clock
class ClockWidget(DesktopWidget):
    def __init__(self, tm, manager) -> None:
        super().__init__("clock", tm, manager)
        self._last_sec = -1
        self._timer = QTimer(self, interval=250, timeout=self._tick)
        self._timer.start()

    def _tick(self) -> None:
        sec = datetime.now().second
        if sec != self._last_sec:
            self._last_sec = sec
            self.update()

    def paint_body(self, p: QPainter, r: QRectF) -> None:
        t = self._tm.theme
        now = datetime.now()
        c = r.center()
        R = min(r.width(), r.height()) / 2 - 15
        p.setBrush(Qt.BrushStyle.NoBrush)
        for i in range(60):
            ang = math.radians(i * 6)
            major = i % 5 == 0
            inner = R - (7 if major else 3.5)
            col = t.color("text" if major else "text_secondary")
            p.setPen(QPen(col, 1.6 if major else 0.9, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
            p.drawLine(QPointF(c.x() + math.sin(ang) * inner, c.y() - math.cos(ang) * inner),
                       QPointF(c.x() + math.sin(ang) * R, c.y() - math.cos(ang) * R))
        self.text(p, QRectF(c.x() - 40, c.y() + R * 0.30, 80, 16), now.strftime("%a %d").upper(),
                  9, "text_secondary", True, Qt.AlignmentFlag.AlignCenter)

        def hand(angle_deg: float, length: float, width: float, color: QColor, tail: float = 0) -> None:
            p.save()
            p.translate(c)
            p.rotate(angle_deg)
            p.setPen(QPen(color, width, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
            p.drawLine(QPointF(0, tail), QPointF(0, -length))
            p.restore()

        hand(((now.hour % 12) + now.minute / 60) * 30, R * 0.50, 4.2, t.color("text"))
        hand((now.minute + now.second / 60) * 6, R * 0.78, 3.0, t.color("text"))
        hand(now.second * 6, R * 0.86, 1.4, t.color("accent"), tail=R * 0.16)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(t.color("accent"))
        p.drawEllipse(c, 3.8, 3.8)


# ============================================================================ System
class SystemWidget(DesktopWidget):
    def __init__(self, tm, manager) -> None:
        super().__init__("system", tm, manager)
        self._anchor = (os.environ.get("SystemDrive", "C:") + "\\") if winapi.IS_WINDOWS else "/"
        self._vals = [0.0, 0.0, 0.0]
        psutil.cpu_percent(interval=None)
        self._timer = QTimer(self, interval=1500, timeout=self._poll)
        self._timer.start()
        self._poll()

    def _poll(self) -> None:
        try:
            disk = psutil.disk_usage(self._anchor).percent
        except OSError:
            disk = 0.0
        self._vals = [psutil.cpu_percent(interval=None), psutil.virtual_memory().percent, disk]
        self.update()

    def paint_body(self, p: QPainter, r: QRectF) -> None:
        t = self._tm.theme
        for i, (label, val) in enumerate(zip(("CPU", "Memory", "Disk"), self._vals)):
            top = 20 + i * 44
            self.text(p, QRectF(18, top, 80, 16), label, 12, "text_secondary", True)
            self.text(p, QRectF(r.width() - 78, top, 60, 16), f"{val:.0f}%", 12, "text", True,
                      Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            track = QRectF(18, top + 22, r.width() - 36, 7)
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(t.color("panel_tile"))
            p.drawRoundedRect(track, 3.5, 3.5)
            fill = QRectF(track.left(), track.top(), max(7.0, track.width() * min(val, 100) / 100), 7)
            p.setBrush(t.color("danger" if val >= 88 else "accent"))
            p.drawRoundedRect(fill, 3.5, 3.5)


# ============================================================================ Calendar
class CalendarWidget(DesktopWidget):
    def __init__(self, tm, manager, week_start: int = 0) -> None:
        super().__init__("calendar", tm, manager)
        today = date.today()
        self._year, self._month = today.year, today.month
        self.week_start = week_start
        self._timer = QTimer(self, interval=60_000, timeout=self.update)
        self._timer.start()

    def _shift(self, delta: int) -> None:
        month = self._month - 1 + delta
        self._year += month // 12
        self._month = month % 12 + 1
        self.update()

    def _arrow_rects(self) -> tuple[QRectF, QRectF]:
        w = self.width()
        return QRectF(w - 70, 12, 26, 26), QRectF(w - 40, 12, 26, 26)

    def mousePressEvent(self, e) -> None:
        pos = e.position()
        left, right = self._arrow_rects()
        if e.button() == Qt.MouseButton.LeftButton:
            if left.contains(pos):
                return self._shift(-1)
            if right.contains(pos):
                return self._shift(1)
            if QRectF(14, 12, 170, 26).contains(pos):   # title resets to today
                today = date.today()
                self._year, self._month = today.year, today.month
                return self.update()
        super().mousePressEvent(e)

    def paint_body(self, p: QPainter, r: QRectF) -> None:
        t = self._tm.theme
        title = date(self._year, self._month, 1).strftime("%B %Y")
        self.text(p, QRectF(18, 12, 200, 26), title, 15, "text", True)
        for rect, glyph in zip(self._arrow_rects(), ("\u2039", "\u203A")):
            self.text(p, rect, glyph, 20, "text_secondary", True, Qt.AlignmentFlag.AlignCenter)

        cal = calendar.Calendar(firstweekday=self.week_start)
        names = [calendar.day_abbr[d][:2].upper() for d in cal.iterweekdays()]
        cell_w = (r.width() - 32) / 7
        for i, name in enumerate(names):
            self.text(p, QRectF(16 + i * cell_w, 44, cell_w, 18), name, 10, "text_secondary", True,
                      Qt.AlignmentFlag.AlignCenter)
        today = date.today()
        for row, week in enumerate(cal.monthdayscalendar(self._year, self._month)):
            for col, day in enumerate(week):
                if not day:
                    continue
                cell = QRectF(16 + col * cell_w, 66 + row * 31, cell_w, 30)
                is_today = (self._year, self._month, day) == (today.year, today.month, today.day)
                if is_today:
                    p.setPen(Qt.PenStyle.NoPen)
                    p.setBrush(t.color("accent"))
                    p.drawEllipse(cell.center(), 13.5, 13.5)
                    p.setPen(QColor(255, 255, 255))     # white text on the accent disc
                    p.setFont(self._tm.font(13, True))
                    p.drawText(cell, Qt.AlignmentFlag.AlignCenter, str(day))
                else:
                    self.text(p, cell, str(day), 13, "text", False, Qt.AlignmentFlag.AlignCenter)


# ============================================================================ Weather
class WeatherWidget(DesktopWidget):
    loaded = pyqtSignal(object)

    def __init__(self, tm, manager, settings: Settings) -> None:
        super().__init__("weather", tm, manager)
        self._settings = settings
        self._data: dict | None = None
        self._status = "Loading\u2026"
        self._place: dict | None = None
        self.loaded.connect(self._on_loaded)
        self._timer = QTimer(self, interval=20 * 60_000, timeout=self.refresh)
        self._timer.start()
        settings.changed.connect(lambda k: self.refresh() if k in ("weather_place", "units") else None)
        QTimer.singleShot(800, self.refresh)

    def refresh(self) -> None:
        threading.Thread(target=self._worker, daemon=True).start()

    def _worker(self) -> None:
        try:
            place = self._settings.get("weather_place")
            if not place:
                place = weather.locate_by_ip()
                if place is None:
                    self.loaded.emit(("error", "Set a city in Settings"))
                    return
            imperial = self._settings.get("units", "metric") == "imperial"
            data = weather.fetch(place["lat"], place["lon"], imperial)
            self.loaded.emit(("ok", place, data))
        except Exception:
            self.loaded.emit(("error", "No connection"))

    def _on_loaded(self, payload) -> None:
        if payload[0] == "ok":
            _tag, self._place, self._data = payload
            self._status = ""
        else:
            self._status = payload[1]
        self.update()

    def paint_body(self, p: QPainter, r: QRectF) -> None:
        t = self._tm.theme
        if self._data is None or self._place is None:
            self.text(p, r, self._status or "Loading\u2026", 14, "text_secondary", True, Qt.AlignmentFlag.AlignCenter)
            return
        unit = "\u00b0"
        label, emoji = weather.describe(self._data["code"], self._data["is_day"])
        self.text(p, QRectF(18, 14, 160, 18), self._place["name"], 13, "text", True)
        self.text(p, QRectF(16, 32, 150, 64), f"{round(self._data['temp'])}{unit}", 46, "text", False)
        emoji_font = QFont()
        emoji_font.setFamilies(EMOJI_FONTS)
        emoji_font.setPixelSize(26)
        p.setFont(emoji_font)
        p.setPen(t.color("text"))
        p.drawText(QRectF(18, 100, 40, 36), Qt.AlignmentFlag.AlignVCenter, emoji)
        self.text(p, QRectF(52, 104, 130, 18), label, 12, "text", True)
        today = self._data["days"][0]
        self.text(p, QRectF(52, 122, 130, 16), f"H:{round(today['hi'])}{unit}  L:{round(today['lo'])}{unit}",
                  11, "text_secondary")

        p.setPen(QPen(t.color("widget_border"), 1))
        p.drawLine(QPointF(190, 18), QPointF(190, r.height() - 18))
        for i, day in enumerate(self._data["days"][1:4]):
            top = 16 + i * 42
            name = datetime.strptime(day["date"], "%Y-%m-%d").strftime("%a")
            self.text(p, QRectF(202, top, 44, 34), name, 12, "text", True)
            _lbl, em = weather.describe(day["code"], True)
            emoji_font.setPixelSize(18)
            p.setFont(emoji_font)
            p.setPen(t.color("text"))
            p.drawText(QRectF(244, top, 28, 34), Qt.AlignmentFlag.AlignCenter, em)
            self.text(p, QRectF(274, top, 56, 34), f"{round(day['hi'])}{unit}/{round(day['lo'])}{unit}",
                      11, "text_secondary", False, Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft)


# ============================================================================ Notes
class NotesWidget(DesktopWidget):
    NO_ACTIVATE = False   # needs keyboard focus

    def __init__(self, tm, manager, settings: Settings) -> None:
        super().__init__("notes", tm, manager)
        self._settings = settings
        self.editor = QPlainTextEdit(self)
        self.editor.setGeometry(14, 40, self.width() - 28, self.height() - 54)
        self.editor.setPlaceholderText("Quick notes\u2026")
        self.editor.setPlainText(settings.get("notes_text", ""))
        self.editor.setFrameShape(QPlainTextEdit.Shape.NoFrame)
        self._save_timer = QTimer(self, singleShot=True, interval=600, timeout=self._save)
        self.editor.textChanged.connect(self._save_timer.start)
        tm.changed.connect(self._style)
        self._style()

    def _style(self) -> None:
        t = self._tm.theme
        self.editor.setFont(self._tm.font(13))
        self.editor.setStyleSheet(
            f"QPlainTextEdit {{ background: transparent; color: {t.rgba('text')}; "
            f"selection-background-color: {t.rgba('accent')}; }}")

    def _save(self) -> None:
        self._settings.set("notes_text", self.editor.toPlainText())

    def paint_body(self, p: QPainter, r: QRectF) -> None:
        self.text(p, QRectF(18, 10, 200, 24), "Notes", 14, "text", True)

    def focusOutEvent(self, e) -> None:
        super().focusOutEvent(e)

    def changeEvent(self, e) -> None:
        super().changeEvent(e)
        if not self.isActiveWindow() and self.isVisible() and not self._manager.peeking:
            winapi.set_window_z(self.hwnd(), "bottom")


# ============================================================================ Manager
class WidgetManager(QObject):
    def __init__(self, tm: ThemeManager, settings: Settings) -> None:
        super().__init__()
        self._tm = tm
        self._settings = settings
        self.peeking = False
        self.widgets: dict[str, DesktopWidget] = {}
        week_start = int(settings.get("week_start", 0))
        self.widgets["weather"] = WeatherWidget(tm, self, settings)
        self.widgets["clock"] = ClockWidget(tm, self)
        self.widgets["system"] = SystemWidget(tm, self)
        self.widgets["calendar"] = CalendarWidget(tm, self, week_start)
        self.widgets["notes"] = NotesWidget(tm, self, settings)
        self._bottom_timer = QTimer(self, interval=2500, timeout=self._push_bottom)
        self._peek_timer = QTimer(self, singleShot=True, interval=12_000, timeout=self.end_peek)
        settings.changed.connect(self._on_setting)

    # ---- state ---------------------------------------------------------------
    def _layout(self) -> dict:
        return dict(self._settings.get("widget_layout", {}))

    def is_visible(self, wid: str) -> bool:
        return bool(self._layout().get(wid, {}).get("visible", DEFAULT_VISIBLE[wid]))

    def set_visible(self, wid: str, visible: bool) -> None:
        layout = self._layout()
        entry = dict(layout.get(wid, {}))
        entry["visible"] = visible
        layout[wid] = entry
        self._settings.set("widget_layout", layout)

    def _default_pos(self, wid: str) -> QPoint:
        geo = self.widgets[wid].screen().geometry()
        col_x = geo.x() + geo.width() - 24 - 338
        y0 = geo.y() + self._tm.theme.metric("bar_height", 28) + 16
        row = 172
        spots = {"weather": (0, 0), "clock": (0, row), "system": (180, row),
                 "calendar": (0, row * 2), "notes": (0, row * 2 + 276)}
        dx, dy = spots[wid]
        return QPoint(col_x + dx, y0 + dy)

    def _apply_visibility(self) -> None:
        layout = self._layout()
        for wid, w in self.widgets.items():
            if self.is_visible(wid):
                if not w.isVisible():
                    pos = layout.get(wid, {})
                    w.move(QPoint(pos["x"], pos["y"]) if "x" in pos else self._default_pos(wid))
                    w.show()
                    winapi.prepare_bar_window(w.hwnd(), noactivate=w.NO_ACTIVATE)
                    winapi.set_window_z(w.hwnd(), "bottom")
            elif w.isVisible():
                w.hide()

    def _on_setting(self, key: str) -> None:
        if key == "widget_layout":
            self._apply_visibility()
        elif key == "week_start":
            self.widgets["calendar"].week_start = int(self._settings.get("week_start", 0))
            self.widgets["calendar"].update()

    def save_positions(self) -> None:
        layout = self._layout()
        for wid, w in self.widgets.items():
            entry = dict(layout.get(wid, {}))
            entry.update(x=w.x(), y=w.y(), visible=self.is_visible(wid))
            layout[wid] = entry
        self._settings.set("widget_layout", layout)

    def reset_positions(self) -> None:
        layout = {wid: {"visible": self.is_visible(wid)} for wid in self.widgets}
        self._settings.set("widget_layout", layout)
        for wid, w in self.widgets.items():
            w.move(self._default_pos(wid))

    # ---- lifecycle ------------------------------------------------------------
    def start(self) -> None:
        self._apply_visibility()
        self._bottom_timer.start()

    def stop(self) -> None:
        self._bottom_timer.stop()
        for w in self.widgets.values():
            w.hide()

    def _push_bottom(self) -> None:
        if self.peeking:
            return
        for w in self.widgets.values():
            if w.isVisible() and not (not w.NO_ACTIVATE and w.isActiveWindow()):
                winapi.set_window_z(w.hwnd(), "bottom")

    # ---- peek (bring widgets above everything for a moment) --------------------
    def toggle_peek(self) -> None:
        self.end_peek() if self.peeking else self._begin_peek()

    def _begin_peek(self) -> None:
        self.peeking = True
        for w in self.widgets.values():
            if w.isVisible():
                winapi.set_window_z(w.hwnd(), "top")
        self._peek_timer.start()

    def end_peek(self) -> None:
        if not self.peeking:
            return
        self.peeking = False
        self._peek_timer.stop()
        for w in self.widgets.values():
            if w.isVisible():
                winapi.set_window_z(w.hwnd(), "normal")
                winapi.set_window_z(w.hwnd(), "bottom")

    # ---- menus ----------------------------------------------------------------
    def build_menu(self, menu: StyledMenu) -> None:
        for wid, title in TITLES.items():
            act = menu.addAction(title)
            act.setCheckable(True)
            act.setChecked(self.is_visible(wid))
            act.triggered.connect(lambda checked, w=wid: self.set_visible(w, checked))
        menu.addSeparator()
        menu.addAction("Reset Widget Positions").triggered.connect(self.reset_positions)

    def show_menu(self, widget: DesktopWidget, global_pos: QPoint) -> None:
        menu = StyledMenu(self._tm)
        menu.addAction(f"Hide {TITLES[widget.wid]}").triggered.connect(
            lambda: self.set_visible(widget.wid, False))
        menu.addSeparator()
        self.build_menu(menu)
        menu.exec(global_pos)
