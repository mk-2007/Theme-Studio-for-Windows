"""Global hotkeys via RegisterHotKey, delivered through Qt's native event filter."""
from __future__ import annotations

from ctypes import wintypes
from typing import Callable

from PyQt6.QtCore import QAbstractNativeEventFilter, QTimer

from . import winapi


class HotkeyManager(QAbstractNativeEventFilter):
    def __init__(self) -> None:
        super().__init__()
        self._callbacks: dict[int, Callable[[], None]] = {}
        self._next_id = 1

    def register(self, modifiers: int, vk: int, callback: Callable[[], None]) -> bool:
        hotkey_id = self._next_id
        if not winapi.register_hotkey(hotkey_id, modifiers | winapi.MOD_NOREPEAT, vk):
            return False
        self._callbacks[hotkey_id] = callback
        self._next_id += 1
        return True

    def unregister_all(self) -> None:
        for hotkey_id in list(self._callbacks):
            winapi.unregister_hotkey(hotkey_id)
        self._callbacks.clear()

    def nativeEventFilter(self, event_type, message):
        if winapi.IS_WINDOWS and bytes(event_type) == b"windows_generic_MSG":
            msg = wintypes.MSG.from_address(int(message))
            if msg.message == winapi.WM_HOTKEY:
                callback = self._callbacks.get(int(msg.wParam))
                if callback:
                    QTimer.singleShot(0, callback)
                    return True, 0
        return False, 0
