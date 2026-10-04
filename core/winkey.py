"""Make a lone Windows-key tap (and Ctrl+Esc) open Theme Studio's Launchpad instead of the Start menu.

Privacy/security design (this is a keyboard hook, so it is deliberately minimal):
  * It runs in its own thread, so a slow UI can never delay the system's keyboard input.
  * The callback only asks "was this the Windows key, and was another key pressed while it was held?".
    It never stores, logs or forwards key codes or text, and it never reads what you type.
  * All other keys pass straight through untouched. Key events injected by other programs are ignored.
  * It stays out of the way in full-screen apps and games.
  * It can be switched off in Settings -> Advanced, and it uninstalls itself when the app quits.
"""
from __future__ import annotations

import ctypes
import os
import threading
from ctypes import wintypes

from PyQt6.QtCore import QObject, pyqtSignal

from . import winapi

VK_LWIN, VK_RWIN, VK_ESCAPE = 0x5B, 0x5C, 0x1B
_SHIFT, _CTRL, _ALT = {0x10, 0xA0, 0xA1}, {0x11, 0xA2, 0xA3}, {0x12, 0xA4, 0xA5}
VK_MASK = 0xE8              # unassigned key code, used to tell Windows "the Win key was part of a combo"
LLKHF_INJECTED = 0x10
WH_KEYBOARD_LL = 13
WM_KEYDOWN, WM_KEYUP, WM_SYSKEYDOWN, WM_SYSKEYUP, WM_QUIT = 0x100, 0x101, 0x104, 0x105, 0x12


class WinKeyLogic:
    """Pure state machine (unit-testable). feed() returns (swallow_this_event, action_or_None)."""

    def __init__(self) -> None:
        self.win_down = False
        self.combo = False
        self.ctrl = self.shift = self.alt = False
        self._swallow_esc_up = False

    def feed(self, vk: int, down: bool, injected: bool) -> tuple[bool, str | None]:
        if injected:
            return False, None
        if vk in (VK_LWIN, VK_RWIN):
            if down:
                if not self.win_down:
                    self.win_down, self.combo = True, False
                return False, None
            solo = self.win_down and not self.combo
            self.win_down = self.combo = False
            return False, "win_solo" if solo else None
        if vk in _CTRL:
            self.ctrl = down
        elif vk in _SHIFT:
            self.shift = down
        elif vk in _ALT:
            self.alt = down
        if down and self.win_down:
            self.combo = True                       # Win+D, Win+E, Win+Space ... are left alone
        if vk == VK_ESCAPE:
            if down and self.ctrl and not self.shift and not self.alt and not self.win_down:
                self._swallow_esc_up = True
                return True, "ctrl_esc"             # Ctrl+Esc (not Ctrl+Shift+Esc = Task Manager)
            if not down and self._swallow_esc_up:
                self._swallow_esc_up = False
                return True, None
        return False, None


if winapi.IS_WINDOWS:
    user32 = winapi.user32
    kernel32 = winapi._dll("kernel32")
    HOOKPROC = ctypes.WINFUNCTYPE(ctypes.c_ssize_t, ctypes.c_int, wintypes.WPARAM, wintypes.LPARAM)

    class KBDLLHOOKSTRUCT(ctypes.Structure):
        _fields_ = [("vkCode", wintypes.DWORD), ("scanCode", wintypes.DWORD), ("flags", wintypes.DWORD),
                    ("time", wintypes.DWORD), ("dwExtraInfo", ctypes.c_size_t)]

    class _KEYBDINPUT(ctypes.Structure):
        _fields_ = [("wVk", wintypes.WORD), ("wScan", wintypes.WORD), ("dwFlags", wintypes.DWORD),
                    ("time", wintypes.DWORD), ("dwExtraInfo", ctypes.c_size_t)]

    class _MOUSEINPUT(ctypes.Structure):
        _fields_ = [("dx", wintypes.LONG), ("dy", wintypes.LONG), ("mouseData", wintypes.DWORD),
                    ("dwFlags", wintypes.DWORD), ("time", wintypes.DWORD), ("dwExtraInfo", ctypes.c_size_t)]

    class _HARDWAREINPUT(ctypes.Structure):
        _fields_ = [("uMsg", wintypes.DWORD), ("wParamL", wintypes.WORD), ("wParamH", wintypes.WORD)]

    class _INPUTUNION(ctypes.Union):
        _fields_ = [("ki", _KEYBDINPUT), ("mi", _MOUSEINPUT), ("hi", _HARDWAREINPUT)]

    class INPUT(ctypes.Structure):
        _fields_ = [("type", wintypes.DWORD), ("u", _INPUTUNION)]

    user32.SetWindowsHookExW.argtypes = [ctypes.c_int, HOOKPROC, wintypes.HINSTANCE, wintypes.DWORD]
    user32.SetWindowsHookExW.restype = ctypes.c_void_p
    user32.CallNextHookEx.argtypes = [ctypes.c_void_p, ctypes.c_int, wintypes.WPARAM, wintypes.LPARAM]
    user32.CallNextHookEx.restype = ctypes.c_ssize_t
    user32.UnhookWindowsHookEx.argtypes = [ctypes.c_void_p]
    user32.GetMessageW.argtypes = [ctypes.POINTER(wintypes.MSG), wintypes.HWND, wintypes.UINT, wintypes.UINT]
    user32.PostThreadMessageW.argtypes = [wintypes.DWORD, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM]
    user32.SendInput.argtypes = [wintypes.UINT, ctypes.POINTER(INPUT), ctypes.c_int]
    kernel32.GetModuleHandleW.argtypes = [wintypes.LPCWSTR]
    kernel32.GetModuleHandleW.restype = wintypes.HMODULE
    kernel32.GetCurrentThreadId.restype = wintypes.DWORD


def _send_mask_key() -> None:
    """Press+release an unassigned key so Windows treats the Win key as used and skips the Start menu."""
    inputs = (INPUT * 2)()
    for i, flags in enumerate((0, 0x0002)):        # key down, key up
        inputs[i].type = 1
        inputs[i].u.ki = _KEYBDINPUT(VK_MASK, 0, flags, 0, 0)
    user32.SendInput(2, inputs, ctypes.sizeof(INPUT))


class WinKeyHook(QObject):
    triggered = pyqtSignal()          # a solo Win tap or Ctrl+Esc happened

    def __init__(self) -> None:
        super().__init__()
        self._logic = WinKeyLogic()
        self._thread: threading.Thread | None = None
        self._thread_id = 0
        self._hook = None
        self._proc = None              # keep the callback alive
        self._ready = threading.Event()

    @property
    def active(self) -> bool:
        return self._thread is not None and self._thread.is_alive() and bool(self._hook)

    def start(self) -> bool:
        if not winapi.IS_WINDOWS or self.active:
            return self.active
        self._ready.clear()
        self._thread = threading.Thread(target=self._run, name="winkey-hook", daemon=True)
        self._thread.start()
        self._ready.wait(2.0)
        return self.active

    def stop(self) -> None:
        if winapi.IS_WINDOWS and self._thread is not None:
            if self._thread_id:
                user32.PostThreadMessageW(self._thread_id, WM_QUIT, 0, 0)
            self._thread.join(1.5)
        self._thread, self._hook = None, None

    # ---- hook thread
    def _run(self) -> None:
        self._thread_id = kernel32.GetCurrentThreadId()
        self._proc = HOOKPROC(self._callback)
        self._hook = user32.SetWindowsHookExW(WH_KEYBOARD_LL, self._proc, kernel32.GetModuleHandleW(None), 0)
        self._ready.set()
        if not self._hook:
            return
        msg = wintypes.MSG()
        while user32.GetMessageW(ctypes.byref(msg), None, 0, 0) > 0:
            pass
        user32.UnhookWindowsHookEx(self._hook)
        self._hook = None

    def _callback(self, n_code: int, w_param: int, l_param: int) -> int:
        try:
            if n_code >= 0 and w_param in (WM_KEYDOWN, WM_KEYUP, WM_SYSKEYDOWN, WM_SYSKEYUP):
                info = ctypes.cast(l_param, ctypes.POINTER(KBDLLHOOKSTRUCT)).contents
                swallow, action = self._logic.feed(info.vkCode, w_param in (WM_KEYDOWN, WM_SYSKEYDOWN),
                                                   bool(info.flags & LLKHF_INJECTED))
                if action and not winapi.foreground_is_fullscreen_app(os.getpid()):
                    if action == "win_solo":
                        _send_mask_key()
                    self.triggered.emit()
                elif action:
                    swallow = False                     # full-screen app: let Windows handle the key normally
                if swallow:
                    return 1
        except Exception:
            pass                                        # never let an error break keyboard input
        return user32.CallNextHookEx(None, n_code, w_param, l_param)
