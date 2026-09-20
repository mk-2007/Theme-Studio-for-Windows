"""Recolors other apps' title bars to match the active theme (Windows 11; harmless elsewhere)."""
from __future__ import annotations

from PyQt6.QtCore import QObject

from . import winapi
from .apps import AppTracker
from .settings import Settings
from .theme import ThemeManager

# theme id -> (caption RGB, text RGB)
_PALETTE = {
    "macos_dark": ((44, 44, 46), (236, 236, 240)),
    "macos_light": ((236, 236, 238), (38, 38, 40)),
    "ubuntu_dark": ((44, 44, 44), (238, 238, 238)),
    "ubuntu_light": ((235, 235, 235), (48, 48, 48)),
}


class WindowStyler(QObject):
    def __init__(self, tm: ThemeManager, tracker: AppTracker, settings: Settings) -> None:
        super().__init__()
        self._tm, self._tracker, self._settings = tm, tracker, settings
        self._styled: set[int] = set()
        tracker.changed.connect(self.apply)
        tm.changed.connect(self.reapply)
        settings.changed.connect(lambda k: self.reapply() if k == "style_windows" else None)

    def enabled(self) -> bool:
        return bool(self._settings.get("style_windows", True)) and winapi.IS_WINDOWS

    def apply(self) -> None:
        if not self.enabled():
            return
        current = set(self._tracker.window_handles())
        self._styled &= current
        theme = self._tm.theme
        caption, text = _PALETTE.get(theme.id, _PALETTE["macos_dark"] if theme.mode == "dark"
                                     else _PALETTE["macos_light"])
        for hwnd in current - self._styled:
            winapi.style_titlebar(hwnd, caption, text, theme.mode == "dark")
            self._styled.add(hwnd)

    def reapply(self) -> None:
        if not self.enabled():
            self.reset_all()
            return
        self._styled.clear()
        self.apply()

    def reset_all(self) -> None:
        for hwnd in list(self._styled):
            winapi.reset_titlebar(hwnd)
        self._styled.clear()
