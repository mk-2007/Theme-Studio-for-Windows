"""The dock: macOS-style floating pill or Ubuntu-style side panel, with smart auto-hide."""
from __future__ import annotations

import math
import os
import subprocess
import time
from dataclasses import dataclass

from PyQt6.QtCore import QPoint, QPointF, QRect, QRectF, Qt, QTimer, pyqtSignal
from PyQt6.QtGui import QColor, QCursor, QFontMetrics, QLinearGradient, QPainter, QPen
from PyQt6.QtWidgets import QWidget

from core import winapi
from core.apps import AppTracker, DockItem, launch_item
from core.settings import Settings
from core.theme import ThemeManager
from .icons import IconCache, paint_launchpad, paint_trash
from .widgets import StyledMenu

DEFAULT_ICON = 44
GAP = 8              # spacing between icons (pill)
PANEL_GAP = 6        # spacing between icons (panel)
SEP = 10             # width of the divider
PAD_X = 12           # pill padding along the dock
EDGE = 4             # default gap between a floating pill and the screen edge (Settings: dock_edge_gap)
SLACK = 130          # extra window length for the pill to grow into while magnifying
MAX_SCALE = 1.65


@dataclass
class Slot:
    kind: str                 # "launchpad" | "app" | "sep" | "trash"
    item: DockItem | None
    x: float = 0.0            # position along the dock (virtual "u" axis)
    size: float = 0.0


class WorkAreaReserver(QWidget):
    """Invisible, click-through strip that keeps maximized windows clear of the dock."""

    def __init__(self) -> None:
        super().__init__(None, Qt.WindowType.Tool
                         | Qt.WindowType.FramelessWindowHint
                         | Qt.WindowType.WindowStaysOnTopHint
                         | Qt.WindowType.WindowTransparentForInput)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
        self._appbar: winapi.AppBar | None = None
        self._edge = -1

    def reserve(self, thickness: int, position: str) -> QRect:
        """Reserve `thickness` logical px on the bottom/left edge; returns the strip (logical px)."""
        screen = self.screen()
        geo = screen.geometry()
        edge = winapi.ABE_LEFT if position == "left" else winapi.ABE_BOTTOM

        def fallback() -> QRect:
            if position == "left":
                return QRect(geo.x(), geo.y(), thickness, geo.height())
            return QRect(geo.x(), geo.y() + geo.height() - thickness, geo.width(), thickness)

        if not winapi.IS_WINDOWS:  # preview mode
            rect = fallback()
            self.setGeometry(rect)
            return rect
        if self._appbar is not None and edge != self._edge:
            self._appbar.remove()
            self._appbar = None
        self.show()
        hwnd = int(self.winId())
        winapi.prepare_bar_window(hwnd)
        if self._appbar is None:
            self._appbar = winapi.AppBar(hwnd, edge)
            self._appbar.register()
            self._edge = edge
        dpr = screen.devicePixelRatio()
        rc = self._appbar.position(round(thickness * dpr))
        if rc is None:
            return fallback()
        left, top, right, bottom = rc
        return QRect(round(left / dpr), round(top / dpr),
                     round((right - left) / dpr), round((bottom - top) / dpr))

    def release(self) -> None:
        if self._appbar is not None:
            self._appbar.remove()
            self._appbar = None
        self.hide()


class Dock(QWidget):
    launchpad_requested = pyqtSignal()

    def __init__(self, tm: ThemeManager, tracker: AppTracker, settings: Settings, icons: IconCache) -> None:
        super().__init__(None, Qt.WindowType.Tool
                         | Qt.WindowType.FramelessWindowHint
                         | Qt.WindowType.WindowStaysOnTopHint)
        self._tm = tm
        self._tracker = tracker
        self._settings = settings
        self._icons = icons
        self._reserver = WorkAreaReserver()
        self._strip = QRect()
        self._length = 600
        self._apply_metrics()

        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
        self.setMouseTracking(True)
        self.setAcceptDrops(True)
        self.setWindowTitle("Theme Studio Dock")

        self._items: list[DockItem] = []
        self._slots: list[Slot] = []
        self._pill = QRectF()
        self._trash_full = False

        # magnification / hover animation
        self._inside = False
        self._mx = 0.0
        self._mx_target = 0.0
        self._inf = 0.0
        self._inf_target = 0.0
        self._hover = -1
        self._pressed = -1
        self._bounce: dict[str, float] = {}
        self._anim = QTimer(self, interval=16, timeout=self._tick)

        # auto-hide
        self._slide = 0.0          # 0 = shown, 1 = hidden
        self._slide_target = 0.0
        self._hide_since = 0.0
        self._slide_timer = QTimer(self, interval=16, timeout=self._slide_tick)
        self._vis_timer = QTimer(self, interval=90, timeout=self._visibility_tick)
        self._trash_timer = QTimer(self, interval=3000, timeout=self._poll_trash)

        tracker.changed.connect(self._on_items_changed)
        tm.changed.connect(self.update)
        settings.changed.connect(self._on_setting)

    # ================================================================ metrics / settings
    def _apply_metrics(self) -> None:
        s = self._settings
        self._position = "left" if s.get("dock_position", "bottom") == "left" else "bottom"
        self._vertical = self._position == "left"
        self._panel = s.get("dock_style", "pill") == "panel"
        self._mode = s.get("dock_mode", "smart")
        self._icon = max(32, min(72, int(s.get("dock_icon_size", DEFAULT_ICON))))
        self._max_scale = MAX_SCALE if (s.get("dock_magnify", True) and not self._panel) else 1.0
        self._sigma = 62.0 * self._icon / 48
        self._gap = PANEL_GAP if self._panel else GAP
        self._edge = 0 if self._panel else max(0, min(24, int(s.get("dock_edge_gap", EDGE))))
        self._bar_t = self._icon + (22 if self._panel else 18)          # thickness of the visible bar
        if self._vertical:
            self._win_t = self._bar_t + self._edge + 230                # room for hover labels
        else:
            self._win_t = self._bar_t + self._edge + int(self._icon * 0.7) + 70
        self._reserved = self._bar_t if self._panel else self._bar_t + self._edge + 4

    def _on_setting(self, key: str) -> None:
        if key not in ("dock_icon_size", "dock_magnify", "dock_position", "dock_style", "dock_mode", "dock_edge_gap"):
            return
        was_always = self._mode == "always"
        self._apply_metrics()
        self._slide = self._slide_target = 0.0
        self.reposition()
        if was_always and self._mode != "always":       # the work area needs a moment to grow back
            QTimer.singleShot(350, self.reposition)
        self._sync_timers()
        self.update()

    def _sync_timers(self) -> None:
        if self._mode == "always":
            self._vis_timer.stop()
            self._slide = self._slide_target = 0.0
            if not self.isVisible():
                self.show()
            self._place()
        else:
            self._vis_timer.start()

    # ================================================================ lifecycle
    def start(self) -> None:
        self._on_items_changed()
        self.show()
        self.reposition()
        self._poll_trash()
        self._trash_timer.start()
        self._sync_timers()

    def stop(self) -> None:
        for timer in (self._trash_timer, self._anim, self._vis_timer, self._slide_timer):
            timer.stop()
        self._reserver.release()
        self.hide()

    def reposition(self) -> None:
        """(Re)reserve or free screen space, then size and place the dock."""
        if self._mode == "always":
            self._strip = self._reserver.reserve(self._reserved, self._position)
        else:
            self._reserver.release()
            geo = self.screen().geometry()               # the true screen edge, not the work area
            top = self.screen().availableGeometry().y()  # ...but stay below the top bar
            t = self._reserved
            if self._vertical:
                self._strip = QRect(geo.x(), top, t, geo.y() + geo.height() - top)
            else:
                self._strip = QRect(geo.x(), geo.y() + geo.height() - t, geo.width(), t)
        self._fit_size()
        if winapi.IS_WINDOWS:
            winapi.prepare_bar_window(int(self.winId()))
        self._place()

    def _fit_size(self) -> None:
        slots = self._make_slots()
        base_total = sum(self._base_size(s) + self._gap for s in slots) - self._gap
        scr = self.screen().geometry()
        max_len = scr.height() if self._vertical else scr.width()
        if self._panel:
            strip_len = self._strip.height() if self._vertical else self._strip.width()
            length = strip_len if strip_len > 0 else max_len
        else:
            length = min(base_total + 2 * PAD_X + 2 * SLACK, max_len)
        self._length = int(length)
        if self._vertical:
            self.setFixedSize(self._win_t, self._length)
        else:
            self.setFixedSize(self._length, self._win_t)

    def _target_pos(self, offset: int) -> QPoint:
        strip, w, h = self._strip, self.width(), self.height()
        if not self._vertical:
            x = strip.x() if self._panel else strip.center().x() - w // 2
            return QPoint(x, strip.bottom() + 1 - h + offset)
        y = strip.y() if self._panel else strip.center().y() - h // 2
        return QPoint(strip.left() - offset, y)

    def _place(self) -> None:
        if self._strip.isNull():
            return
        off = int(self._slide * (self._bar_t + self._edge + 12))
        pos = self._target_pos(off)
        self.setGeometry(pos.x(), pos.y(), self.width(), self.height())

    # ================================================================ model
    def _make_slots(self) -> list[Slot]:
        apps = [Slot("app", it) for it in self._items]
        if self._panel:
            return apps + [Slot("sep", None), Slot("trash", None), Slot("launchpad", None)]
        return [Slot("launchpad", None)] + apps + [Slot("sep", None), Slot("trash", None)]

    def _base_size(self, slot: Slot) -> float:
        return SEP if slot.kind == "sep" else self._icon

    def _on_items_changed(self) -> None:
        self._items = self._tracker.items()
        for item in self._items:                      # a launched app has appeared
            if item.running:
                self._bounce.pop(item.key, None)
        self._fit_size()
        self._compute_layout()
        self._place()
        self._hover = -1
        self.update()

    def _poll_trash(self) -> None:
        full = winapi.recycle_bin_items() > 0
        if full != self._trash_full:
            self._trash_full = full
            self.update()

    # ================================================================ coordinate mapping
    # The dock is laid out as if it were a horizontal bar at the bottom ("virtual" space:
    # u runs along the dock, v across it, v=T at the screen edge). For a left dock the
    # virtual space is rotated onto the window with these helpers.
    def _mp(self, u: float, v: float) -> QPointF:
        return QPointF(self._win_t - v, u) if self._vertical else QPointF(u, v)

    def _mr(self, r: QRectF) -> QRectF:
        if not self._vertical:
            return QRectF(r)
        return QRectF(self._win_t - (r.y() + r.height()), r.x(), r.height(), r.width())

    def _unmap(self, pos: QPointF) -> QPointF:
        return QPointF(pos.y(), self._win_t - pos.x()) if self._vertical else QPointF(pos)

    # ================================================================ layout
    def _icon_v_bottom(self, slot: Slot) -> float:
        T = float(self._win_t)
        if self._panel:
            return T - self._bar_t / 2 + slot.size / 2
        return T - self._edge - 9

    def _compute_layout(self) -> None:
        slots = self._make_slots()
        base = [self._base_size(s) for s in slots]
        n, gap = len(slots), self._gap
        L, T = float(self._length), float(self._win_t)

        if self._panel:                              # fixed layout: apps at the start, system items at the end
            x = 10.0
            for slot, b in zip(slots[:-3], base[:-3]):
                slot.x, slot.size = x, b
                x += b + gap
            x = L - 10.0
            for slot, b in zip(reversed(slots[-3:]), reversed(base[-3:])):
                x -= b
                slot.x, slot.size = x, b
                x -= gap
            self._slots = slots
            self._pill = QRectF(0, T - self._bar_t, L, self._bar_t)
            return

        base_total = sum(b + gap for b in base) - gap
        base_left = (L - base_total) / 2
        centers, x = [], base_left
        for b in base:
            centers.append(x + b / 2)
            x += b + gap

        sizes = []
        for slot, b, c in zip(slots, base, centers):
            if slot.kind == "sep":
                sizes.append(b)
            else:
                d = self._mx - c
                bump = math.exp(-(d * d) / (2 * self._sigma * self._sigma))
                sizes.append(b * (1 + (self._max_scale - 1) * self._inf * bump))

        total = sum(s + gap for s in sizes) - gap
        centered_left = (L - total) / 2
        left = centered_left
        if self._inf > 0.001 and self._max_scale > 1.0:
            k, frac, x = n - 1, 1.0, base_left       # keep what is under the cursor under the cursor
            for i, b in enumerate(base):
                extent = b + gap
                if self._mx < x + extent or i == n - 1:
                    k, frac = i, min(max((self._mx - x) / extent, 0.0), 1.0)
                    break
                x += extent
            before = sum(sizes[i] + gap for i in range(k))
            anchored = self._mx - (before + frac * (sizes[k] + gap))
            left = centered_left + (anchored - centered_left) * self._inf

        x = left
        for slot, size in zip(slots, sizes):
            slot.x, slot.size = x, size
            x += size + gap
        self._slots = slots
        self._pill = QRectF(left - PAD_X, T - self._edge - self._bar_t, total + 2 * PAD_X, self._bar_t)

    def _slot_win_rect(self, slot: Slot, lift: float = 0.0) -> QRectF:
        vb = self._icon_v_bottom(slot)
        return self._mr(QRectF(slot.x, vb - slot.size - lift, slot.size, slot.size))

    def _hit(self, pos: QPointF) -> int:
        if not self._slots:
            return -1
        v = self._unmap(pos)
        T = float(self._win_t)
        for i, slot in enumerate(self._slots):
            if slot.kind == "sep":
                continue
            if self._panel:
                lo, hi = T - self._bar_t, T
                inside_u = slot.x - self._gap / 2 <= v.x() <= slot.x + slot.size + self._gap / 2
            else:
                lo, hi = self._icon_v_bottom(slot) - slot.size - 14, T - self._edge
                inside_u = slot.x <= v.x() <= slot.x + slot.size
            if inside_u and lo <= v.y() <= hi:
                return i
        return -1

    # ================================================================ animation
    def _needs_anim(self) -> bool:
        return (abs(self._inf - self._inf_target) > 0.003
                or abs(self._mx - self._mx_target) > 0.4
                or bool(self._bounce))

    def _start_anim(self) -> None:
        if not self._anim.isActive():
            self._anim.start()

    def _tick(self) -> None:
        self._inf += (self._inf_target - self._inf) * 0.22
        if abs(self._inf - self._inf_target) < 0.003:
            self._inf = self._inf_target
        self._mx += (self._mx_target - self._mx) * 0.4
        self.update()
        if not self._needs_anim():
            self._anim.stop()

    def _bounce_offset(self, key: str) -> float:
        t0 = self._bounce.get(key)
        if t0 is None:
            return 0.0
        dt = time.monotonic() - t0
        if dt > 8.0:
            self._bounce.pop(key, None)
            return 0.0
        return abs(math.sin(dt * 5.2)) * 20 * max(0.35, 1 - dt / 10)

    # ================================================================ auto-hide
    def _bar_rect_global(self, at_rest: bool) -> QRectF:
        pos = self._target_pos(0) if at_rest else self.pos()
        reach = self._icon * 0.8 + 30                    # room for magnified icons
        rect = self._mr(self._pill).translated(QPointF(pos))
        if self._vertical:
            return rect.adjusted(-6, -6, reach, 6)
        return rect.adjusted(-6, -reach, 6, 6)

    def _cursor_near(self, cur: QPoint) -> bool:
        if self._slide < 0.6 and self._bar_rect_global(at_rest=False).contains(QPointF(cur)):
            return True
        scr = self.screen().geometry()
        rest = self._bar_rect_global(at_rest=True)
        if self._vertical:
            at_edge = cur.x() <= scr.left() + 1
            in_band = self._panel or rest.top() - 120 <= cur.y() <= rest.bottom() + 120
        else:
            at_edge = cur.y() >= scr.bottom() - 1
            in_band = self._panel or rest.left() - 120 <= cur.x() <= rest.right() + 120
        return at_edge and in_band

    def _overlapped(self) -> bool:
        bar = self._bar_rect_global(at_rest=True)
        dpr = self.screen().devicePixelRatio()
        for hwnd in self._tracker.window_handles():
            if winapi.is_minimized(hwnd):
                continue
            rect = winapi.get_window_rect(hwnd)
            if rect is None:
                continue
            win = QRectF(rect[0] / dpr, rect[1] / dpr, (rect[2] - rect[0]) / dpr, (rect[3] - rect[1]) / dpr)
            if win.intersects(bar):
                return True
        return False

    def _visibility_tick(self) -> None:
        if self._mode == "always":
            return
        near = self._cursor_near(QCursor.pos())
        hide = (not near) if self._mode == "autohide" else (not near and self._overlapped())
        now = time.monotonic()
        target = self._slide_target
        if hide:
            self._hide_since = self._hide_since or now
            if now - self._hide_since > 0.4:
                target = 1.0
        else:
            self._hide_since = 0.0
            target = 0.0
        if target != self._slide_target:
            self._slide_target = target
            self._slide_timer.start()

    def _slide_tick(self) -> None:
        if self._slide_target < self._slide and not self.isVisible():
            self.show()
            if winapi.IS_WINDOWS:
                winapi.set_window_z(int(self.winId()), "top")
        self._slide += (self._slide_target - self._slide) * 0.28
        if abs(self._slide - self._slide_target) < 0.02:
            self._slide = self._slide_target
            self._slide_timer.stop()
        self._place()
        if self._slide >= 0.999:
            self.hide()

    # ================================================================ painting
    def paintEvent(self, _event) -> None:
        self._compute_layout()
        theme = self._tm.theme
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        p.setRenderHint(QPainter.RenderHint.TextAntialiasing)
        T = float(self._win_t)
        body = self._mr(self._pill)

        if self._panel:
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(theme.color("dock_bg"))
            p.drawRect(body)
            p.setPen(QPen(theme.color("dock_border"), 1))
            if self._vertical:
                p.drawLine(QPointF(body.right(), body.top()), QPointF(body.right(), body.bottom()))
            else:
                p.drawLine(QPointF(body.left(), body.top()), QPointF(body.right(), body.top()))
        else:
            radius = theme.metric("dock_radius", 22)
            for i in range(1, 5):                                  # soft shadow
                p.setPen(Qt.PenStyle.NoPen)
                p.setBrush(QColor(0, 0, 0, 9))
                p.drawRoundedRect(body.adjusted(-i, -i, i, i), radius + i, radius + i)
            p.setBrush(theme.color("dock_bg"))
            p.drawRoundedRect(body, radius, radius)
            far, near = (body.topRight(), body.topLeft()) if self._vertical else (body.topLeft(), body.bottomLeft())
            glow = QLinearGradient(far, near)
            glow.setColorAt(0.0, theme.color("dock_highlight"))
            glow.setColorAt(0.55, QColor(255, 255, 255, 0))
            p.setBrush(glow)
            p.drawRoundedRect(body, radius, radius)
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.setPen(QPen(theme.color("dock_border"), 1))
            p.drawRoundedRect(body.adjusted(0.5, 0.5, -0.5, -0.5), radius, radius)

        for i, slot in enumerate(self._slots):
            if slot.kind == "sep":
                p.setPen(QPen(theme.color("dock_border"), 1))
                cu = slot.x + slot.size / 2
                v0 = (T - self._bar_t + 14) if self._panel else (T - self._edge - self._bar_t + 14)
                v1 = T - 14 if self._panel else T - self._edge - 14
                p.drawLine(self._mp(cu, v0), self._mp(cu, v1))
                continue

            lift = self._bounce_offset(slot.item.key) if slot.item else 0.0
            rect = self._slot_win_rect(slot, lift)
            if self._panel and (i == self._hover or (slot.item and slot.item.active)):
                p.setPen(Qt.PenStyle.NoPen)
                p.setBrush(theme.color("hover" if i == self._hover else "panel_tile"))
                p.drawRoundedRect(self._slot_win_rect(slot).adjusted(-5, -5, 5, 5), 8, 8)
            p.setOpacity(0.72 if i == self._pressed else 1.0)
            if slot.kind == "trash":
                paint_trash(p, rect, self._trash_full, theme.color("text"))
            elif slot.kind == "launchpad":
                paint_launchpad(p, rect)
            else:
                item = slot.item
                pm = self._icons.get(item.icon_path, item.name)
                p.drawPixmap(rect, pm, QRectF(pm.rect()))
            p.setOpacity(1.0)

            item = slot.item
            if slot.kind == "app" and item and item.running:
                cu = slot.x + slot.size / 2
                p.setPen(Qt.PenStyle.NoPen)
                if self._panel:                                    # one dot per window, on the screen edge
                    count = min(len(item.hwnds), 3)
                    for k in range(count):
                        du = (k - (count - 1) / 2) * 8
                        p.setBrush(theme.color("dock_dot_active" if item.active and k == 0 else "dock_dot"))
                        p.drawEllipse(self._mp(cu + du, T - 4.5), 2.4, 2.4)
                else:
                    p.setBrush(theme.color("dock_dot_active" if item.active else "dock_dot"))
                    p.drawEllipse(self._mp(cu, T - self._edge - 4.5), 2.2, 2.2)

        self._paint_label(p)

    def _paint_label(self, p: QPainter) -> None:
        if not (0 <= self._hover < len(self._slots)) or self._inf < 0.05:
            return
        slot = self._slots[self._hover]
        text = {"trash": "Trash" if self._panel else "Recycle Bin",
                "launchpad": "Show Applications" if self._panel else "Launchpad"}.get(
            slot.kind, slot.item.name if slot.item else "")
        if not text:
            return
        theme = self._tm.theme
        font = self._tm.font(size=12)
        p.setFont(font)
        w = QFontMetrics(font).horizontalAdvance(text) + 22
        h = 26
        icon = self._slot_win_rect(slot)
        if self._vertical:
            rect = QRectF(icon.right() + 16, icon.center().y() - h / 2, w, h)
        else:
            rect = QRectF(min(max(icon.center().x() - w / 2, 4), self.width() - w - 4),
                          max(icon.top() - 12 - h, 2), w, h)
        p.setPen(QPen(theme.color("menu_border"), 1))
        p.setBrush(theme.color("menu_bg"))
        p.drawRoundedRect(rect, 7, 7)
        p.setPen(theme.color("menu_text"))
        p.drawText(rect, Qt.AlignmentFlag.AlignCenter, text)

    # ================================================================ mouse
    def enterEvent(self, event) -> None:
        self._mx = self._mx_target = self._unmap(event.position()).x()
        self._inside = True
        self._inf_target = 1.0
        self._start_anim()

    def leaveEvent(self, _event) -> None:
        self._inside = False
        self._inf_target = 0.0
        self._hover = -1
        self._start_anim()
        self.update()

    def mouseMoveEvent(self, event) -> None:
        u = self._unmap(event.position()).x()
        if not self._inside:
            self._inside = True
            self._mx = u
        self._mx_target = u
        self._inf_target = 1.0
        self._hover = self._hit(event.position())
        self._start_anim()
        self.update()

    def mousePressEvent(self, event) -> None:
        self._pressed = self._hit(event.position())
        self.update()

    def mouseReleaseEvent(self, event) -> None:
        idx = self._hit(event.position())
        pressed, self._pressed = self._pressed, -1
        if idx >= 0 and idx == pressed:
            if event.button() == Qt.MouseButton.LeftButton:
                self._on_click(self._slots[idx])
            elif event.button() == Qt.MouseButton.RightButton:
                self._on_context(self._slots[idx])
        self.update()

    # ================================================================ actions
    def _on_click(self, slot: Slot) -> None:
        if slot.kind == "launchpad":
            self.launchpad_requested.emit()
            return
        if slot.kind == "trash":
            if winapi.IS_WINDOWS:
                os.startfile("shell:RecycleBinFolder")  # type: ignore[attr-defined]
            return
        item = slot.item
        if item is None:
            return
        if not item.running:
            if launch_item(item):
                self._bounce[item.key] = time.monotonic()
                self._start_anim()
            return
        hwnds = item.hwnds
        if item.active:
            fg = winapi.get_foreground_window()
            if len(hwnds) == 1:
                winapi.window_command(hwnds[0], "minimize")   # click the active app: minimize
            else:
                nxt = hwnds[(hwnds.index(fg) + 1) % len(hwnds)] if fg in hwnds else hwnds[0]
                winapi.activate_window(nxt)                   # cycle through its windows
        else:
            winapi.activate_window(hwnds[0])
        QTimer.singleShot(150, self._tracker.refresh)

    def _menu_anchor(self, slot: Slot, menu: StyledMenu) -> QPoint:
        rect = self._slot_win_rect(slot)
        if self._vertical:
            return self.mapToGlobal(QPoint(int(rect.right()) + 10, int(rect.top())))
        pos = self.mapToGlobal(QPoint(int(rect.left()), int(rect.top()) - 8))
        return QPoint(pos.x(), pos.y() - menu.sizeHint().height())

    def _on_context(self, slot: Slot) -> None:
        if slot.kind == "launchpad":
            return
        menu = StyledMenu(self._tm)
        if slot.kind == "trash":
            menu.addAction("Open Recycle Bin").triggered.connect(
                lambda: os.startfile("shell:RecycleBinFolder") if winapi.IS_WINDOWS else None)  # type: ignore[attr-defined]
            empty = menu.addAction("Empty Recycle Bin\u2026")
            empty.setEnabled(self._trash_full)
            empty.triggered.connect(lambda: (winapi.empty_recycle_bin(), QTimer.singleShot(1500, self._poll_trash)))
        elif slot.item is not None:
            item = slot.item
            menu.addAction(item.name).setEnabled(False)
            if item.running:
                menu.addSeparator()
                for hwnd in item.hwnds[:8]:
                    title = winapi.get_window_title(hwnd) or item.name
                    if len(title) > 44:
                        title = title[:43] + "\u2026"
                    menu.addAction(title).triggered.connect(lambda _c=False, h=hwnd: winapi.activate_window(h))
            menu.addSeparator()
            if item.running:
                menu.addAction("New Window").triggered.connect(lambda: launch_item(item))
            if item.pinned:
                menu.addAction("Remove from Dock").triggered.connect(lambda: self._tracker.unpin(item.key))
            elif item.can_pin:
                menu.addAction("Keep in Dock").triggered.connect(lambda: self._tracker.pin(item))
            if item.exe and os.path.exists(item.exe):
                menu.addAction("Show in Explorer").triggered.connect(
                    lambda: subprocess.Popen(["explorer.exe", f"/select,{item.exe}"]) if winapi.IS_WINDOWS else None)
            if item.running:
                menu.addSeparator()
                menu.addAction("Quit").triggered.connect(
                    lambda: [winapi.window_command(h, "close") for h in item.hwnds])
        menu.exec(self._menu_anchor(slot, menu))
        QTimer.singleShot(400, self._tracker.refresh)

    # ================================================================ drag & drop
    def dragEnterEvent(self, event) -> None:
        if event.mimeData().hasUrls():
            event.acceptProposedAction()

    def dropEvent(self, event) -> None:
        for url in event.mimeData().urls():
            if url.isLocalFile():
                self._tracker.pin_path(url.toLocalFile())
        event.acceptProposedAction()
