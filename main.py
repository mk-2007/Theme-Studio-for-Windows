"""Theme Studio - macOS-style desktop shell layer for Windows."""
from __future__ import annotations

import argparse
import atexit
import os
import signal
import subprocess
import sys
import time

from PyQt6.QtCore import QDir, QLockFile, QTimer
from PyQt6.QtNetwork import QLocalServer, QLocalSocket
from PyQt6.QtGui import QIcon
from PyQt6.QtWidgets import QApplication, QMenu, QMessageBox, QSystemTrayIcon

from core import guard, logsetup, profiles, selfinstall, system, winapi
from core.winkey import WinKeyHook
from core.apps import AppTracker
from core.hardware import Brightness, Volume
from core.paths import resource_root
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
IPC_NAME = "ThemeStudio.ipc"


def parse_args() -> argparse.Namespace:
    ap = argparse.ArgumentParser(description=APP_NAME)
    ap.add_argument("--hide-taskbar", action="store_true",
                    help="hide the Windows taskbar while Theme Studio runs")
    ap.add_argument("--restore-taskbar", action="store_true",
                    help="bring the Windows taskbar back and exit (use after a crash)")
    ap.add_argument("--keep-taskbar", action="store_true",
                    help="leave the Windows taskbar alone (it is hidden by default)")
    ap.add_argument("--guard", type=int, default=None, help=argparse.SUPPRESS)      # internal
    ap.add_argument("--wait-pid", type=int, default=None, help=argparse.SUPPRESS)   # internal (restart)
    ap.add_argument("--no-install-prompt", action="store_true", help=argparse.SUPPRESS)
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
        self._tray_peek = False
        self._tray_peek_since = 0.0
        self._is_down = False
        self._settings_dialog: SettingsDialog | None = None

        # ---- core services
        self.index = AppIndex()
        self.icons = IconCache()
        self.icons.set_style(self.settings.get("icon_style", "plate"))
        self.volume, self.brightness = Volume(), Brightness()
        self.tracker = AppTracker(self.settings)
        self.winkey = WinKeyHook()
        self.winkey.triggered.connect(self._on_winkey)

        # ---- UI pieces
        self.bar = MenuBar(self.tm, self.settings)
        self.dock = None if args.no_dock else Dock(self.tm, self.tracker, self.settings, self.icons)
        self.widgets = None if args.no_widgets else WidgetManager(self.tm, self.settings)
        self.desktop_icons = DesktopIcons(self.tm, self.icons, self.settings)
        self.styler = WindowStyler(self.tm, self.tracker, self.settings)
        self.launchpad = Launchpad(self.tm, self.index, self.icons, self.settings)
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
        self.bar.tray_requested.connect(self.peek_tray)
        if self.dock is not None:
            self.dock.launchpad_requested.connect(self.launchpad.toggle)
        self.control_center.dark_mode_requested.connect(self.toggle_dark_mode)
        self.tm.changed.connect(self._persist_theme_variant)
        self.control_center.settings_requested.connect(self.open_settings)
        self.control_center.peek_requested.connect(self.peek_widgets)
        self.settings.changed.connect(self._on_setting)

        self.hotkeys = HotkeyManager()
        app.installNativeEventFilter(self.hotkeys)
        self._taskbar_timer = QTimer(interval=1200, timeout=self._enforce_taskbar)
        self._tray_watch = QTimer(interval=500, timeout=self._tray_watch_tick)
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

    def _persist_theme_variant(self) -> None:
        mode = self.settings.get("profile", "macos")
        profiles.set_mode_pref(self.settings, mode, "theme_variant", self.tm.theme.mode)

    def _persist_widget_visibility(self) -> None:
        mode = self.settings.get("profile", "macos")
        layout = self.settings.get("widget_layout", {})
        for wid, entry in layout.items():
            if "visible" in entry:
                profiles.set_mode_widget(self.settings, mode, wid, entry["visible"])

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
        elif key == "win_key_launchpad":
            self._sync_winkey()
        elif key == "widget_layout":
            self._persist_widget_visibility()
        elif key == "dock_icon_size":
            profiles.set_mode_pref(self.settings, self.settings.get("profile", "macos"),
                                   "dock_icon_size", self.settings.get("dock_icon_size"))

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
        self._sync_winkey()
        self._taskbar_timer.start()
        QTimer.singleShot(900, self.redock)       # the work area settles after the taskbar hides
        self._watch_screens()

    def _on_winkey(self) -> None:
        if self.settings.get("win_key_launchpad", True):
            self.launchpad.toggle()

    def _sync_winkey(self) -> None:
        want = bool(self.settings.get("win_key_launchpad", True)) and winapi.IS_WINDOWS
        if want and not self.winkey.active:
            if not self.winkey.start():
                print("[warn] could not install the Windows-key hook; Win will still open the normal Start menu")
        elif not want and self.winkey.active:
            self.winkey.stop()

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
        ico = resource_root() / "assets" / "theme_studio.ico"
        icon = QIcon(str(ico)) if ico.exists() else make_logo_icon(self.tm.theme.color("accent"))
        self.tray = QSystemTrayIcon(icon, self.app)
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
        menu.addAction("Open log file").triggered.connect(lambda: system.open_uri(str(logsetup.log_path())))
        menu.addAction(f"Restart {APP_NAME}").triggered.connect(self.restart)
        if selfinstall.is_frozen() and selfinstall.running_from_install_dir():
            menu.addAction(f"Uninstall {APP_NAME}\u2026").triggered.connect(self.uninstall)
        menu.addAction(f"Quit {APP_NAME}").triggered.connect(self.quit)
        self._tray_menu = menu  # keep a reference
        self.tray.setContextMenu(menu)
        self.tray.show()

    # ---------------------------------------------------------------- taskbar
    def _enforce_taskbar(self) -> None:
        if self._taskbar_hidden and not self._tray_peek:
            winapi.enforce_taskbar_hidden()

    def peek_tray(self) -> None:
        """Show the real taskbar briefly so its notification area (tray icons) can be used."""
        if not winapi.IS_WINDOWS:
            return
        if self._tray_peek:
            self.end_tray_peek()
            return
        self._tray_peek = True
        self._tray_peek_since = time.monotonic()
        winapi.show_taskbar_for_tray()
        self._tray_watch.start()

    def _tray_watch_tick(self) -> None:
        age = time.monotonic() - self._tray_peek_since
        if age > 12 or (age > 3 and not winapi.cursor_over_taskbar()):
            self.end_tray_peek()

    def end_tray_peek(self) -> None:
        self._tray_peek = False
        self._tray_watch.stop()
        if self._taskbar_hidden:
            winapi.enforce_taskbar_hidden()

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
        self.winkey.stop()
        self._taskbar_timer.stop()
        self._tray_watch.stop()
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
        guard.mark_clean()

    def quit(self) -> None:
        self.shutdown()
        self.app.quit()

    def uninstall(self) -> None:
        if QMessageBox.question(None, "Uninstall", f"Remove {APP_NAME} from this PC?") \
                != QMessageBox.StandardButton.Yes:
            return
        self.shutdown()
        winapi.restore_taskbar()
        winapi.set_desktop_icons_visible(True)
        selfinstall.uninstall()
        self.app.quit()

    def restart(self) -> None:
        cmd = [sys.executable]
        if not getattr(sys, "frozen", False):
            cmd.append(os.path.abspath(sys.argv[0]))
        cmd += ["--wait-pid", str(os.getpid())]
        try:
            subprocess.Popen(cmd, creationflags=0x08000000 if winapi.IS_WINDOWS else 0)
        except OSError as exc:
            print(f"[restart] failed: {exc}")
            return
        self.quit()


def _handle_ipc(server: QLocalServer, studio: Studio) -> None:
    conn = server.nextPendingConnection()
    if conn is None:
        return

    def read() -> None:
        message = bytes(conn.readAll()).decode("utf-8", "ignore").strip()
        if message == "settings":
            studio.open_settings()
        elif message == "launchpad":
            studio.launchpad.toggle()
    conn.readyRead.connect(read)


def main() -> int:
    args = parse_args()
    if args.guard is not None:                 # background safety-net process, no UI
        return guard.run_guard(args.guard)
    if args.restore_taskbar:
        winapi.restore_taskbar()
        winapi.set_desktop_icons_visible(True)
        print("Windows taskbar and desktop icons restored.")
        return 0

    logsetup.setup()
    if args.wait_pid is not None:              # restarting: let the old instance finish first
        guard.wait_for_pid(args.wait_pid)
        time.sleep(0.4)
    if winapi.IS_WINDOWS and winapi.is_elevated():
        print("Refusing to run elevated (as Administrator). Restart it normally.")
        try:
            _a = QApplication.instance() or QApplication(sys.argv)
            QMessageBox.warning(None, APP_NAME,
                                f"{APP_NAME} does not need, and should not run with, administrator rights.\n\n"
                                "Please close this and start it normally instead.")
        except Exception:
            pass
        return 1
    if not winapi.IS_WINDOWS:
        print("Note: Theme Studio targets Windows; running in preview mode.")

    app = QApplication(sys.argv)
    app.setApplicationName(APP_NAME)
    app.setQuitOnLastWindowClosed(False)
    ico = resource_root() / "assets" / "theme_studio.ico"
    if ico.exists():
        app.setWindowIcon(QIcon(str(ico)))

    if selfinstall.should_offer_install() and not args.no_install_prompt:
        box = QMessageBox()
        box.setWindowTitle(f"{APP_NAME} setup")
        box.setText(f"Install {APP_NAME} on this PC?")
        box.setInformativeText("It will start with Windows, add Start-menu and desktop shortcuts, and replace "
                               "the Windows taskbar. You can quit any time with Ctrl+Alt+Q.")
        install_btn = box.addButton("Install", QMessageBox.ButtonRole.AcceptRole)
        box.addButton("Just run it once", QMessageBox.ButtonRole.RejectRole)
        box.setDefaultButton(install_btn)
        box.exec()
        if box.clickedButton() is install_btn:
            try:
                selfinstall.launch(selfinstall.install())
                return 0
            except Exception as exc:
                QMessageBox.warning(None, "Setup failed", f"Could not install: {exc}")
                return 1

    lock = QLockFile(QDir.temp().filePath("theme_studio.lock"))
    if not lock.tryLock(100):
        # Already running: ask the running copy to open Settings, then exit quietly.
        sock = QLocalSocket()
        sock.connectToServer(IPC_NAME)
        if sock.waitForConnected(800):
            sock.write(b"settings")
            sock.waitForBytesWritten(800)
        print(f"{APP_NAME} is already running.")
        return 0

    guard.mark_running()
    guard.spawn_guard()
    studio = Studio(app, args)
    atexit.register(studio.shutdown)
    signal.signal(signal.SIGINT, lambda *_: studio.quit())
    QTimer(app, interval=250, timeout=lambda: None).start()  # lets Python handle Ctrl+C

    QLocalServer.removeServer(IPC_NAME)
    server = QLocalServer(app)
    if server.listen(IPC_NAME):
        server.newConnection.connect(lambda: _handle_ipc(server, studio))

    studio.start()
    code = app.exec()
    studio.shutdown()
    lock.unlock()
    return code


if __name__ == "__main__":
    sys.exit(main())
