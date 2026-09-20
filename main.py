"""Theme Studio - macOS-style desktop shell layer for Windows."""
from __future__ import annotations

import argparse
import atexit
import signal
import sys

from PyQt6.QtCore import QDir, QLockFile, QTimer
from PyQt6.QtWidgets import QApplication, QMenu, QMessageBox, QSystemTrayIcon

from core import profiles, system, winapi
from core.apps import AppTracker
from core.hardware import Brightness, Volume
from core.hotkeys import HotkeyManager
from core.index import AppIndex
from core.settings import Settings
from core.theme import ThemeManager
from core.winstyle import WindowStyler
from ui.control_center import ControlCenter
from ui.desktop_icons import DesktopIcons
from ui.desktop_widgets import WidgetManager
from ui.dock import Dock
from ui.icons import IconCache
from ui.launchpad import Launchpad
from ui.menubar import APP_NAME, MenuBar
from ui.settings_dialog import SettingsDialog
from ui.spotlight import Spotlight
from ui.widgets import make_logo_icon

VK_SPACE = 0x20


def parse_args() -> argparse.Namespace:
    ap = argparse.ArgumentParser(description=APP_NAME)
    ap.add_argument("--hide-taskbar", action="store_true",
                    help="hide the Windows taskbar while Theme Studio runs")
    ap.add_argument("--restore-taskbar", action="store_true",
                    help="bring the Windows taskbar back and exit (use after a crash)")
    ap.add_argument("--keep-taskbar", action="store_true",
                    help="leave the Windows taskbar alone (it is hidden by default)")
    ap.add_argument("--no-dock", action="store_true", help="no dock")
    ap.add_argument("--no-widgets", action="store_true", help="no desktop widgets")
    ap.add_argument("--theme", default=None, help="theme id, e.g. macos_dark or macos_light")
    return ap.parse_args()


class Studio:
    def __init__(self, app: QApplication, args: argparse.Namespace):
        self.app = app
        self.settings = Settings()
        self.tm = ThemeManager()
        self.tm.set_theme(args.theme or self.settings.get("theme", "macos_dark"))
        if self.settings.get("profile") is None:          # first run: start from the macOS style
            profiles.apply_profile(self.settings, self.tm, "macos")
        self.tm.changed.connect(lambda: self.settings.set("theme", self.tm.theme.id))

        self._want_hidden_taskbar = (not args.keep_taskbar) and \
            (args.hide_taskbar or bool(self.settings.get("hide_taskbar", True)))
        self._taskbar_hidden = False
        self._is_down = False
        self._settings_dialog: SettingsDialog | None = None

        # ---- core services
        self.index = AppIndex()
        self.icons = IconCache()
        self.icons.set_style(self.settings.get("icon_style", "plate"))
        self.volume, self.brightness = Volume(), Brightness()
        self.tracker = AppTracker(self.settings)

        # ---- UI pieces
        self.bar = MenuBar(self.tm, self.settings)
        self.dock = None if args.no_dock else Dock(self.tm, self.tracker, self.settings, self.icons)
        self.widgets = None if args.no_widgets else WidgetManager(self.tm, self.settings)
        self.desktop_icons = DesktopIcons(self.tm, self.icons, self.settings)
        self.styler = WindowStyler(self.tm, self.tracker, self.settings)
        self.launchpad = Launchpad(self.tm, self.index, self.icons)
        self.spotlight = Spotlight(self.tm, self.index, self.icons, self._commands())
        self.control_center = ControlCenter(self.tm, self.volume, self.brightness)

        # ---- wiring
        self.bar.set_widget_manager(self.widgets)
        self.bar.quit_requested.connect(self.quit)
        self.bar.restore_taskbar_requested.connect(self.restore_taskbar)
        self.bar.spotlight_requested.connect(self.spotlight.toggle)
        self.bar.launchpad_requested.connect(self.launchpad.toggle)
        self.bar.settings_requested.connect(self.open_settings)
        self.bar.peek_requested.connect(self.peek_widgets)
        self.bar.control_center_requested.connect(self.control_center.show_at)
        self.bar.profile_requested.connect(self.set_profile)
        if self.dock is not None:
            self.dock.launchpad_requested.connect(self.launchpad.toggle)
        self.control_center.dark_mode_requested.connect(self.toggle_dark_mode)
        self.control_center.settings_requested.connect(self.open_settings)
        self.control_center.peek_requested.connect(self.peek_widgets)
        self.settings.changed.connect(self._on_setting)

        self.hotkeys = HotkeyManager()
        app.installNativeEventFilter(self.hotkeys)
        self._redock_timer = QTimer(singleShot=True, interval=300)
        self._redock_timer.timeout.connect(self.redock)
        self._build_tray()

    # ---------------------------------------------------------------- commands
    def _commands(self) -> dict:
        return {
            "lock": ("Lock Screen", system.lock_screen),
            "sleep": ("Sleep", system.sleep),
            "restart": ("Restart\u2026", lambda: self._confirm("Restart", system.restart)),
            "shut down": ("Shut Down\u2026", lambda: self._confirm("Shut Down", system.shutdown)),
            "dark mode": ("Toggle Dark / Light Mode", self.toggle_dark_mode),
            "settings": (f"{APP_NAME} Settings", self.open_settings),
            "windows settings": ("Windows Settings", system.open_system_settings),
            "task manager": ("Task Manager", system.open_task_manager),
            "launchpad": ("Launchpad", lambda: self.launchpad.open_pad()),
            "widgets": ("Peek at Widgets", self.peek_widgets),
            "macos style": ("Switch to macOS style", lambda: self.set_profile("macos")),
            "ubuntu style": ("Switch to Ubuntu style", lambda: self.set_profile("ubuntu")),
            "quit theme studio": (f"Quit {APP_NAME}", self.quit),
        }

    @staticmethod
    def _confirm(verb: str, action) -> None:
        if QMessageBox.question(None, verb, f"Are you sure you want to {verb.lower().rstrip('.')} now?") \
                == QMessageBox.StandardButton.Yes:
            action()

    # ---------------------------------------------------------------- actions
    def toggle_dark_mode(self) -> None:
        self.tm.toggle_mode()
        winapi.set_windows_dark_mode(self.tm.theme.mode == "dark")

    def peek_widgets(self) -> None:
        if self.widgets is not None:
            self.widgets.toggle_peek()

    def open_settings(self) -> None:
        if self._settings_dialog is None:
            self._settings_dialog = SettingsDialog(self.tm, self.settings, self.widgets)
        dlg = self._settings_dialog
        dlg.show()
        dlg.raise_()
        dlg.activateWindow()
        if winapi.IS_WINDOWS:
            winapi.activate_window(int(dlg.winId()))

    def set_profile(self, name: str) -> None:
        profiles.apply_profile(self.settings, self.tm, name)

    def _on_setting(self, key: str) -> None:
        if key == "hide_taskbar":
            self.hide_taskbar() if self.settings.get("hide_taskbar", True) else self.restore_taskbar()
        elif key == "icon_style":
            self.icons.set_style(self.settings.get("icon_style", "plate"))
            for piece in (self.dock, self.launchpad, self.spotlight, self.desktop_icons):
                if piece is not None:
                    piece.update()
        elif key == "desktop_icons":
            self.desktop_icons.refresh_enabled()

    # ---------------------------------------------------------------- start
    def start(self) -> None:
        self.index.build_async()
        if self._want_hidden_taskbar:
            self.hide_taskbar()
        self.bar.show()
        self.bar.dock()
        self.tracker.start()
        if self.dock is not None:
            self.dock.start()
        if self.widgets is not None:
            self.widgets.start()
        self.desktop_icons.start()
        self._register_hotkeys()
        QTimer.singleShot(900, self.redock)       # the work area settles after the taskbar hides
        self._watch_screens()

    def _register_hotkeys(self) -> None:
        wanted = [
            (winapi.MOD_CONTROL | winapi.MOD_ALT, ord("Q"), self.quit, "Ctrl+Alt+Q (quit)"),
            (winapi.MOD_ALT, VK_SPACE, self.spotlight.toggle, "Alt+Space (Spotlight)"),
            (winapi.MOD_CONTROL | winapi.MOD_ALT, ord("L"), self.launchpad.toggle, "Ctrl+Alt+L (Launchpad)"),
            (winapi.MOD_CONTROL | winapi.MOD_ALT, ord("W"), self.peek_widgets, "Ctrl+Alt+W (widgets)"),
        ]
        for mods, vk, callback, label in wanted:
            if not self.hotkeys.register(mods, vk, callback) and winapi.IS_WINDOWS:
                print(f"[warn] could not register {label}; another app may be using it")

    def redock(self) -> None:
        self.bar.dock()
        if self.dock is not None:
            self.dock.reposition()
        if self.desktop_icons.isVisible():
            self.desktop_icons.setGeometry(self.desktop_icons.screen().geometry())

    def _watch_screens(self) -> None:
        def hook(screen) -> None:
            screen.geometryChanged.connect(lambda *_: self._redock_timer.start())
        for screen in self.app.screens():
            hook(screen)
        self.app.screenAdded.connect(lambda s: (hook(s), self._redock_timer.start()))
        self.app.screenRemoved.connect(lambda *_: self._redock_timer.start())
        self.app.primaryScreenChanged.connect(lambda *_: self._redock_timer.start())

    # ---------------------------------------------------------------- tray
    def _build_tray(self) -> None:
        self.tray = QSystemTrayIcon(make_logo_icon(self.tm.theme.color("accent")), self.app)
        self.tray.setToolTip(f"{APP_NAME}  (Alt+Space: Spotlight, Ctrl+Alt+Q: quit)")
        menu = QMenu()
        menu.addAction("Spotlight").triggered.connect(self.spotlight.toggle)
        menu.addAction("Launchpad").triggered.connect(self.launchpad.toggle)
        menu.addAction("Settings\u2026").triggered.connect(self.open_settings)
        menu.addAction("Toggle dark / light").triggered.connect(self.toggle_dark_mode)
        menu.addAction("macOS style").triggered.connect(lambda: self.set_profile("macos"))
        menu.addAction("Ubuntu style").triggered.connect(lambda: self.set_profile("ubuntu"))
        menu.addSeparator()
        menu.addAction("Hide Windows taskbar").triggered.connect(lambda: self.settings.set("hide_taskbar", True))
        menu.addAction("Restore Windows taskbar").triggered.connect(lambda: self.settings.set("hide_taskbar", False))
        menu.addSeparator()
        menu.addAction(f"Quit {APP_NAME}").triggered.connect(self.quit)
        self._tray_menu = menu  # keep a reference
        self.tray.setContextMenu(menu)
        self.tray.show()

    # ---------------------------------------------------------------- taskbar
    def hide_taskbar(self) -> None:
        winapi.hide_taskbar()
        self._taskbar_hidden = True
        QTimer.singleShot(900, self.redock)

    def restore_taskbar(self) -> None:
        winapi.restore_taskbar()
        self._taskbar_hidden = False
        QTimer.singleShot(900, self.redock)

    # ---------------------------------------------------------------- shutdown
    def shutdown(self) -> None:
        if self._is_down:
            return
        self._is_down = True
        self.hotkeys.unregister_all()
        self.tracker.stop()
        for piece in (self.spotlight, self.launchpad, self.control_center):
            piece.hide()
        if self.widgets is not None:
            self.widgets.stop()
        if self.dock is not None:
            self.dock.stop()
        self.desktop_icons.stop()
        self.styler.reset_all()
        self.bar.undock()
        if self._taskbar_hidden:
            winapi.restore_taskbar()
            self._taskbar_hidden = False

    def quit(self) -> None:
        self.shutdown()
        self.app.quit()


def main() -> int:
    args = parse_args()
    if args.restore_taskbar:
        winapi.restore_taskbar()
        winapi.set_desktop_icons_visible(True)
        print("Windows taskbar and desktop icons restored.")
        return 0

    if not winapi.IS_WINDOWS:
        print("Note: Theme Studio targets Windows; running in preview mode.")

    app = QApplication(sys.argv)
    app.setApplicationName(APP_NAME)
    app.setQuitOnLastWindowClosed(False)

    lock = QLockFile(QDir.temp().filePath("theme_studio.lock"))
    if not lock.tryLock(100):
        print(f"{APP_NAME} is already running.")
        return 1

    studio = Studio(app, args)
    atexit.register(studio.shutdown)
    signal.signal(signal.SIGINT, lambda *_: studio.quit())
    QTimer(app, interval=250, timeout=lambda: None).start()  # lets Python handle Ctrl+C

    studio.start()
    code = app.exec()
    studio.shutdown()
    lock.unlock()
    return code


if __name__ == "__main__":
    sys.exit(main())
