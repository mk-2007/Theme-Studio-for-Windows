"""The top bar: macOS menu bar or GNOME panel, with optional auto-hide."""
from __future__ import annotations

from datetime import datetime

from PyQt6.QtCore import QPoint, QRect, Qt, QTimer, pyqtSignal
import time

from PyQt6.QtGui import QCursor, QPainter
from PyQt6.QtWidgets import QApplication, QHBoxLayout, QMessageBox, QWidget

from core import system, winapi
from core.settings import Settings
from core.theme import ThemeManager
from . import glyphs
from .widgets import BarButton, BatteryIndicator, GlyphButton, LogoButton, StyledMenu

APP_NAME = "Theme Studio"


class MenuBar(QWidget):
    quit_requested = pyqtSignal()
    restore_taskbar_requested = pyqtSignal()
    spotlight_requested = pyqtSignal()
    control_center_requested = pyqtSignal(int, int)   # global right edge, global bottom of bar
    peek_requested = pyqtSignal()
    settings_requested = pyqtSignal()
    launchpad_requested = pyqtSignal()
    profile_requested = pyqtSignal(str)
    tray_requested = pyqtSignal()

    def __init__(self, tm: ThemeManager, settings: Settings):
        super().__init__(None, Qt.WindowType.Tool
                         | Qt.WindowType.FramelessWindowHint
                         | Qt.WindowType.WindowStaysOnTopHint)
        self._tm = tm
        self._settings = settings
        self._widget_manager = None
        self._appbar: winapi.AppBar | None = None
        self._blur_ok = False
        self._target_hwnd = 0

        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
        self.setWindowTitle(APP_NAME)
        self.setFixedHeight(tm.theme.metric("bar_height", 28))

        # -- widgets (all built once; _relayout() picks the ones each layout needs)
        self._slide = 0.0
        self._slide_target = 0.0
        self._hide_since = 0.0
        self.logo = LogoButton(tm)
        self.activities = BarButton(tm, "Activities", bold=True, pad=12)
        self.app_btn = BarButton(tm, "Desktop", bold=True)
        self.battery = BatteryIndicator(tm)
        self.cc_btn = GlyphButton(tm, glyphs.draw_controls)
        self.search_btn = GlyphButton(tm, glyphs.draw_search)
        self.wifi_btn = GlyphButton(tm, glyphs.draw_wifi)
        self.vol_btn = GlyphButton(tm, lambda p, r, c: glyphs.draw_speaker(p, r, c, 1.0))
        self.power_btn = GlyphButton(tm, glyphs.draw_power)
        self.tray_btn = GlyphButton(tm, glyphs.draw_chevron)
        self.clock = BarButton(tm, "", pad=10)

        self._layout = QHBoxLayout(self)
        self._layout.setContentsMargins(6, 0, 6, 0)
        self._layout.setSpacing(0)
        self._optional = [self.logo, self.activities, self.app_btn, self.tray_btn, self.battery, self.cc_btn,
                          self.search_btn, self.wifi_btn, self.vol_btn, self.power_btn, self.clock]
        for w in self._optional:          # widgets not in the layout must still belong to the bar
            w.setParent(self)

        self.logo.clicked.connect(self._show_system_menu)
        self.app_btn.clicked.connect(self._show_app_menu)
        self.activities.clicked.connect(self.launchpad_requested.emit)
        self.tray_btn.clicked.connect(self.tray_requested.emit)
        self.search_btn.clicked.connect(self.spotlight_requested.emit)
        for btn in (self.cc_btn, self.wifi_btn, self.vol_btn, self.power_btn):
            btn.clicked.connect(self._open_control_center)
        self.clock.clicked.connect(self.peek_requested.emit)
        tm.changed.connect(self._on_theme_changed)
        settings.changed.connect(self._on_setting)
        self._relayout()

        # -- live data
        self._tick_clock()
        self._tick_battery()
        self._clock_timer = QTimer(self, timeout=self._tick_clock, interval=1000)
        self._battery_timer = QTimer(self, timeout=self._tick_battery, interval=30_000)
        self._fg_timer = QTimer(self, timeout=self._poll_foreground, interval=400)
        self._hide_timer = QTimer(self, timeout=self._autohide_tick, interval=90)
        self._slide_timer = QTimer(self, timeout=self._slide_tick, interval=16)
        for timer in (self._clock_timer, self._battery_timer, self._fg_timer, self._hide_timer):
            timer.start()

    def set_widget_manager(self, manager) -> None:
        self._widget_manager = manager

    # ------------------------------------------------------------ layout profiles
    def _gnome(self) -> bool:
        return self._settings.get("menubar_layout", "macos") == "gnome"

    def _relayout(self) -> None:
        while self._layout.count():
            self._layout.takeAt(0)
        for w in self._optional:
            w.hide()
        if self._gnome():
            left = [self.activities, self.app_btn]
            right = [self.tray_btn, self.battery, self.wifi_btn, self.vol_btn, self.power_btn]
        else:
            left = [self.logo, self.app_btn]
            right = [self.tray_btn, self.battery, self.search_btn, self.cc_btn, self.clock]
        for w in left:
            self._layout.addWidget(w)
            w.show()
        self._layout.addStretch(1)
        for w in right:
            self._layout.addWidget(w)
            w.show()
        if self._gnome():
            self.clock.show()
            self._position_clock()
        self._tick_battery()

    def _position_clock(self) -> None:
        if not self._gnome():
            return
        width = self.clock.sizeHint().width()
        self.clock.setGeometry(max(0, (self.width() - width) // 2), 0, width, self.height())
        self.clock.raise_()

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self._position_clock()

    def _on_setting(self, key: str) -> None:
        if key == "clock_24h":
            self._tick_clock()
        elif key == "menubar_layout":
            self._relayout()
            self._tick_clock()
            self.dock()
        elif key == "menubar_mode":
            self.dock()

    def _open_control_center(self) -> None:
        anchor = self.power_btn if self._gnome() else self.cc_btn
        right = anchor.mapToGlobal(QPoint(anchor.width(), 0)).x() + 6
        top = self.geometry().bottom() + 6
        self.control_center_requested.emit(right, top)

    # ------------------------------------------------------------ docking
    def _autohide(self) -> bool:
        return self._settings.get("menubar_mode", "always") == "autohide"

    def dock(self) -> None:
        """Place the bar: reserve the top strip (always) or float over the screen (auto-hide)."""
        screen = self.screen()
        height_logical = self.height()
        geo = screen.geometry()
        if not winapi.IS_WINDOWS:  # preview mode for non-Windows machines
            self.setGeometry(QRect(geo.x(), geo.y(), geo.width(), height_logical))
            return
        hwnd = int(self.winId())
        winapi.prepare_bar_window(hwnd)
        if self._autohide():
            if self._appbar is not None:
                self._appbar.remove()
                self._appbar = None
            self._slide = self._slide_target = 0.0
            self.setGeometry(geo.x(), geo.y(), geo.width(), height_logical)
        else:
            self._slide = self._slide_target = 0.0
            if self._appbar is None:
                self._appbar = winapi.AppBar(hwnd, winapi.ABE_TOP)
                self._appbar.register()
            self._appbar.position(round(height_logical * screen.devicePixelRatio()))
        self._apply_blur()

    # ---- auto-hide behaviour
    def _autohide_tick(self) -> None:
        if not self._autohide() or not self.isVisible():
            return
        geo = self.screen().geometry()
        cur = QCursor.pos()
        near = (cur.y() <= geo.y() + 1 or (self._slide < 0.5 and cur.y() <= geo.y() + self.height() + 4)
                or QApplication.activePopupWidget() is not None)
        if near:
            self._hide_since = 0.0
            target = 0.0
        else:
            self._hide_since = self._hide_since or time.monotonic()
            target = 1.0 if time.monotonic() - self._hide_since > 0.5 else 0.0
        if target != self._slide_target:
            self._slide_target = target
            self._slide_timer.start()

    def _slide_tick(self) -> None:
        self._slide += (self._slide_target - self._slide) * 0.3
        if abs(self._slide - self._slide_target) < 0.02:
            self._slide = self._slide_target
            self._slide_timer.stop()
        geo = self.screen().geometry()
        self.move(geo.x(), geo.y() - int(self._slide * (self.height() + 1)))

    def undock(self) -> None:
        if self._appbar is not None:
            self._appbar.remove()
            self._appbar = None
        self.hide()

    def _apply_blur(self) -> None:
        if not winapi.IS_WINDOWS:
            return
        tint = self._tm.theme.color("blur_tint")
        self._blur_ok = winapi.enable_blur(int(self.winId()), tint.red(), tint.green(),
                                           tint.blue(), tint.alpha(), acrylic=True)
        self.update()

    # ------------------------------------------------------------ painting
    def paintEvent(self, _event) -> None:
        p = QPainter(self)
        t = self._tm.theme
        # Always paint something: fully transparent layered pixels are click-through.
        p.fillRect(self.rect(), t.color("bar_bg" if self._blur_ok else "bar_bg_fallback"))
        p.setPen(t.color("bar_border"))
        p.drawLine(0, self.height() - 1, self.width(), self.height() - 1)

    # ------------------------------------------------------------ live data
    def _tick_clock(self) -> None:
        now = datetime.now()
        hour = now.hour % 12 or 12
        clock = f"{now:%H:%M}" if self._settings.get("clock_24h", False) else f"{hour}:{now:%M} {now:%p}"
        date_part = f"{now:%b} {now.day}" if self._gnome() else f"{now:%a} {now.day} {now:%b}"
        self.clock.setText(f"{date_part}   {clock}")
        self._position_clock()

    def _tick_battery(self) -> None:
        info = system.battery()
        if info is None:
            self.battery.hide()
        else:
            self.battery.set_state(*info)
            self.battery.show()

    def _poll_foreground(self) -> None:
        info = system.foreground_app()
        if info is None:
            return
        self._target_hwnd, name = info
        self.app_btn.setText(name)

    # ------------------------------------------------------------ theme
    def _on_theme_changed(self) -> None:
        height = self._tm.theme.metric("bar_height", 28)
        if height != self.height():
            self.setFixedHeight(height)
            self.dock()
        self._apply_blur()
        self.update()

    # ------------------------------------------------------------ menus
    def _popup(self, menu: StyledMenu, anchor: QWidget) -> None:
        menu.exec(anchor.mapToGlobal(QPoint(0, self.height())))

    def _show_system_menu(self) -> None:
        m = StyledMenu(self._tm)
        m.addAction(f"About {APP_NAME}").triggered.connect(self._about)
        m.addSeparator()
        m.addAction(f"{APP_NAME} Settings\u2026").triggered.connect(self.settings_requested.emit)
        m.addAction("Launchpad").triggered.connect(self.launchpad_requested.emit)
        if self._widget_manager is not None:
            sub = StyledMenu(self._tm, m)
            sub.setTitle("Widgets")
            self._widget_manager.build_menu(sub)
            m.addMenu(sub)
        styles = StyledMenu(self._tm, m)
        styles.setTitle("Desktop Style")
        for key, label in (("macos", "macOS"), ("ubuntu", "Ubuntu (GNOME)")):
            styles.addAction(label).triggered.connect(lambda _c=False, k=key: self.profile_requested.emit(k))
        m.addMenu(styles)
        m.addSeparator()
        m.addAction("System Settings\u2026").triggered.connect(system.open_system_settings)
        m.addAction("Force Quit\u2026").triggered.connect(system.open_task_manager)
        m.addSeparator()
        m.addAction("Sleep").triggered.connect(system.sleep)
        m.addAction("Restart\u2026").triggered.connect(lambda: self._confirm("Restart", system.restart))
        m.addAction("Shut Down\u2026").triggered.connect(lambda: self._confirm("Shut Down", system.shutdown))
        m.addSeparator()
        m.addAction("Lock Screen").triggered.connect(system.lock_screen)
        m.addSeparator()
        m.addAction("Restore Windows Taskbar").triggered.connect(self.restore_taskbar_requested.emit)
        m.addAction(f"Quit {APP_NAME}").triggered.connect(self.quit_requested.emit)
        self._popup(m, self.logo)

    def _show_app_menu(self) -> None:
        m = StyledMenu(self._tm)
        hwnd = self._target_hwnd
        has_target = bool(hwnd)
        maximize_text = "Restore" if winapi.is_maximized(hwnd) else "Maximize"
        m.addAction("Minimize").triggered.connect(lambda: winapi.window_command(hwnd, "minimize"))
        m.addAction(maximize_text).triggered.connect(lambda: winapi.window_command(hwnd, "maximize"))
        m.addSeparator()
        m.addAction("Close Window").triggered.connect(lambda: winapi.window_command(hwnd, "close"))
        for action in m.actions():
            if not action.isSeparator():
                action.setEnabled(has_target)
        self._popup(m, self.app_btn)

    def _about(self) -> None:
        QMessageBox.about(None, f"About {APP_NAME}",
                          f"{APP_NAME}\nMenu bar, dock, widgets, Launchpad, Spotlight, Control Center.\n"
                          "A macOS-style desktop experience for Windows.")

    def _confirm(self, verb: str, action) -> None:
        answer = QMessageBox.question(None, verb, f"Are you sure you want to {verb.lower()} now?")
        if answer == QMessageBox.StandardButton.Yes:
            action()
