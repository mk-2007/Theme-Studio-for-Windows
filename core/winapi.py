"""Thin ctypes layer over the Win32 APIs Theme Studio needs.

Every function is a safe no-op on non-Windows platforms so the UI can be
previewed elsewhere. No third-party dependency (pywin32) is required.
"""
from __future__ import annotations

import ctypes
import sys
from ctypes import wintypes

IS_WINDOWS = sys.platform == "win32"

# --- constants -------------------------------------------------------------
ABM_NEW, ABM_REMOVE, ABM_QUERYPOS, ABM_SETPOS = 0, 1, 2, 3
ABM_GETSTATE, ABM_SETSTATE = 4, 10
ABE_LEFT, ABE_TOP, ABE_RIGHT, ABE_BOTTOM = 0, 1, 2, 3
ABS_AUTOHIDE, ABS_ALWAYSONTOP = 1, 2

GWL_EXSTYLE = -20
WS_EX_TOOLWINDOW = 0x00000080
WS_EX_APPWINDOW = 0x00040000
WS_EX_NOACTIVATE = 0x08000000

SWP_NOSIZE, SWP_NOMOVE, SWP_NOZORDER = 0x0001, 0x0002, 0x0004
SWP_NOACTIVATE, SWP_FRAMECHANGED, SWP_SHOWWINDOW = 0x0010, 0x0020, 0x0040
HWND_TOPMOST = -1

SW_HIDE, SW_SHOW = 0, 5
WM_SYSCOMMAND = 0x0112
SC_MINIMIZE, SC_MAXIMIZE, SC_CLOSE, SC_RESTORE = 0xF020, 0xF030, 0xF060, 0xF120

MOD_ALT, MOD_CONTROL, MOD_SHIFT, MOD_WIN, MOD_NOREPEAT = 0x1, 0x2, 0x4, 0x8, 0x4000
WM_HOTKEY = 0x0312

WCA_ACCENT_POLICY = 19
ACCENT_ENABLE_BLURBEHIND = 3
ACCENT_ENABLE_ACRYLICBLURBEHIND = 4

MONITOR_DEFAULTTOPRIMARY = 1


# --- structures ------------------------------------------------------------
class APPBARDATA(ctypes.Structure):
    _fields_ = [
        ("cbSize", wintypes.DWORD),
        ("hWnd", wintypes.HWND),
        ("uCallbackMessage", wintypes.UINT),
        ("uEdge", wintypes.UINT),
        ("rc", wintypes.RECT),
        ("lParam", wintypes.LPARAM),
    ]


class ACCENT_POLICY(ctypes.Structure):
    _fields_ = [
        ("AccentState", ctypes.c_int),
        ("AccentFlags", ctypes.c_int),
        ("GradientColor", ctypes.c_uint),
        ("AnimationId", ctypes.c_int),
    ]


class WINDOWCOMPOSITIONATTRIBDATA(ctypes.Structure):
    _fields_ = [
        ("Attribute", ctypes.c_int),
        ("Data", ctypes.c_void_p),
        ("SizeOfData", ctypes.c_size_t),
    ]


class MONITORINFO(ctypes.Structure):
    _fields_ = [
        ("cbSize", wintypes.DWORD),
        ("rcMonitor", wintypes.RECT),
        ("rcWork", wintypes.RECT),
        ("dwFlags", wintypes.DWORD),
    ]


# --- function signatures ---------------------------------------------------
if IS_WINDOWS:
    user32 = ctypes.WinDLL("user32", use_last_error=True)
    shell32 = ctypes.WinDLL("shell32", use_last_error=True)

    def _sig(fn, restype, *argtypes):
        fn.restype = restype
        fn.argtypes = list(argtypes)

    _sig(shell32.SHAppBarMessage, ctypes.c_size_t, wintypes.DWORD, ctypes.POINTER(APPBARDATA))
    _sig(user32.SetWindowPos, wintypes.BOOL, wintypes.HWND, wintypes.HWND,
         ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int, wintypes.UINT)
    _sig(user32.GetWindowLongPtrW, ctypes.c_ssize_t, wintypes.HWND, ctypes.c_int)
    _sig(user32.SetWindowLongPtrW, ctypes.c_ssize_t, wintypes.HWND, ctypes.c_int, ctypes.c_ssize_t)
    _sig(user32.SetWindowCompositionAttribute, wintypes.BOOL, wintypes.HWND,
         ctypes.POINTER(WINDOWCOMPOSITIONATTRIBDATA))
    _sig(user32.MonitorFromPoint, ctypes.c_void_p, wintypes.POINT, wintypes.DWORD)
    _sig(user32.GetMonitorInfoW, wintypes.BOOL, ctypes.c_void_p, ctypes.POINTER(MONITORINFO))
    _sig(user32.FindWindowW, wintypes.HWND, wintypes.LPCWSTR, wintypes.LPCWSTR)
    _sig(user32.FindWindowExW, wintypes.HWND, wintypes.HWND, wintypes.HWND,
         wintypes.LPCWSTR, wintypes.LPCWSTR)
    _sig(user32.ShowWindow, wintypes.BOOL, wintypes.HWND, ctypes.c_int)
    _sig(user32.GetForegroundWindow, wintypes.HWND)
    _sig(user32.GetWindowThreadProcessId, wintypes.DWORD, wintypes.HWND, ctypes.POINTER(wintypes.DWORD))
    _sig(user32.GetClassNameW, ctypes.c_int, wintypes.HWND, wintypes.LPWSTR, ctypes.c_int)
    _sig(user32.GetWindowTextW, ctypes.c_int, wintypes.HWND, wintypes.LPWSTR, ctypes.c_int)
    _sig(user32.PostMessageW, wintypes.BOOL, wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM)
    _sig(user32.IsZoomed, wintypes.BOOL, wintypes.HWND)
    _sig(user32.RegisterHotKey, wintypes.BOOL, wintypes.HWND, ctypes.c_int, wintypes.UINT, wintypes.UINT)
    _sig(user32.UnregisterHotKey, wintypes.BOOL, wintypes.HWND, ctypes.c_int)
    _sig(user32.LockWorkStation, wintypes.BOOL)


# --- window styling --------------------------------------------------------
def prepare_bar_window(hwnd: int, noactivate: bool = True) -> None:
    """Make a window a tool window (no taskbar button); optionally non-activating."""
    if not IS_WINDOWS:
        return
    ex = user32.GetWindowLongPtrW(hwnd, GWL_EXSTYLE)
    ex |= WS_EX_TOOLWINDOW | (WS_EX_NOACTIVATE if noactivate else 0)
    ex &= ~WS_EX_APPWINDOW
    user32.SetWindowLongPtrW(hwnd, GWL_EXSTYLE, ex)
    user32.SetWindowPos(hwnd, None, 0, 0, 0, 0,
                        SWP_NOMOVE | SWP_NOSIZE | SWP_NOZORDER | SWP_NOACTIVATE | SWP_FRAMECHANGED)


def enable_blur(hwnd: int, r: int, g: int, b: int, a: int, acrylic: bool = True) -> bool:
    """Blur what is behind the window. Tint is RGBA 0-255. Returns True on success."""
    if not IS_WINDOWS:
        return False
    accent = ACCENT_POLICY()
    accent.AccentState = ACCENT_ENABLE_ACRYLICBLURBEHIND if acrylic else ACCENT_ENABLE_BLURBEHIND
    accent.AccentFlags = 2
    accent.GradientColor = (a << 24) | (b << 16) | (g << 8) | r  # 0xAABBGGRR
    data = WINDOWCOMPOSITIONATTRIBDATA()
    data.Attribute = WCA_ACCENT_POLICY
    data.Data = ctypes.cast(ctypes.pointer(accent), ctypes.c_void_p)
    data.SizeOfData = ctypes.sizeof(accent)
    return bool(user32.SetWindowCompositionAttribute(hwnd, ctypes.byref(data)))


# --- monitors --------------------------------------------------------------
def primary_monitor_rect() -> tuple[int, int, int, int]:
    """(left, top, right, bottom) of the primary monitor in physical pixels."""
    hmon = user32.MonitorFromPoint(wintypes.POINT(0, 0), MONITOR_DEFAULTTOPRIMARY)
    mi = MONITORINFO()
    mi.cbSize = ctypes.sizeof(MONITORINFO)
    user32.GetMonitorInfoW(hmon, ctypes.byref(mi))
    r = mi.rcMonitor
    return r.left, r.top, r.right, r.bottom


# --- AppBar (reserves screen space, like the macOS menu bar) ----------------
class AppBar:
    def __init__(self, hwnd: int, edge: int = ABE_TOP):
        self.hwnd = hwnd
        self.edge = edge
        self.registered = False

    def _abd(self) -> APPBARDATA:
        abd = APPBARDATA()
        abd.cbSize = ctypes.sizeof(APPBARDATA)
        abd.hWnd = self.hwnd
        return abd

    def register(self) -> None:
        if not IS_WINDOWS or self.registered:
            return
        shell32.SHAppBarMessage(ABM_NEW, ctypes.byref(self._abd()))
        self.registered = True

    def position(self, thickness_px: int) -> tuple[int, int, int, int] | None:
        """Claim `thickness_px` along the edge, move the window there, and return
        the claimed rect (left, top, right, bottom) in physical pixels."""
        if not IS_WINDOWS:
            return None
        left, top, right, bottom = primary_monitor_rect()
        abd = self._abd()
        abd.uEdge = self.edge
        abd.rc.left, abd.rc.top, abd.rc.right, abd.rc.bottom = left, top, right, bottom
        self._fit(abd.rc, thickness_px)
        shell32.SHAppBarMessage(ABM_QUERYPOS, ctypes.byref(abd))
        self._fit(abd.rc, thickness_px)          # QUERYPOS may have moved the far edge
        shell32.SHAppBarMessage(ABM_SETPOS, ctypes.byref(abd))
        rc = abd.rc
        user32.SetWindowPos(self.hwnd, wintypes.HWND(HWND_TOPMOST), rc.left, rc.top,
                            rc.right - rc.left, rc.bottom - rc.top,
                            SWP_NOACTIVATE | SWP_SHOWWINDOW)
        return rc.left, rc.top, rc.right, rc.bottom

    def _fit(self, rc, thickness: int) -> None:
        if self.edge == ABE_TOP:
            rc.bottom = rc.top + thickness
        elif self.edge == ABE_BOTTOM:
            rc.top = rc.bottom - thickness
        elif self.edge == ABE_LEFT:
            rc.right = rc.left + thickness
        else:
            rc.left = rc.right - thickness

    def remove(self) -> None:
        if not IS_WINDOWS or not self.registered:
            return
        shell32.SHAppBarMessage(ABM_REMOVE, ctypes.byref(self._abd()))
        self.registered = False


# --- Windows taskbar hide / restore -----------------------------------------
_saved_taskbar_state: int | None = None


def _taskbar_windows() -> list[int]:
    found = []
    main = user32.FindWindowW("Shell_TrayWnd", None)
    if main:
        found.append(main)
    hwnd = None
    while True:  # secondary monitors
        hwnd = user32.FindWindowExW(None, hwnd, "Shell_SecondaryTrayWnd", None)
        if not hwnd:
            break
        found.append(hwnd)
    return found


def _set_taskbar_state(flags: int) -> None:
    main = user32.FindWindowW("Shell_TrayWnd", None)
    if not main:
        return
    abd = APPBARDATA()
    abd.cbSize = ctypes.sizeof(APPBARDATA)
    abd.hWnd = main
    abd.lParam = flags
    shell32.SHAppBarMessage(ABM_SETSTATE, ctypes.byref(abd))


def hide_taskbar() -> None:
    """Auto-hide (frees the reserved work area) and hide the Windows taskbar."""
    global _saved_taskbar_state
    if not IS_WINDOWS:
        return
    main = user32.FindWindowW("Shell_TrayWnd", None)
    if main and _saved_taskbar_state is None:
        abd = APPBARDATA()
        abd.cbSize = ctypes.sizeof(APPBARDATA)
        abd.hWnd = main
        _saved_taskbar_state = int(shell32.SHAppBarMessage(ABM_GETSTATE, ctypes.byref(abd)))
    _set_taskbar_state(ABS_AUTOHIDE)
    for hwnd in _taskbar_windows():
        user32.ShowWindow(hwnd, SW_HIDE)


def restore_taskbar() -> None:
    global _saved_taskbar_state
    if not IS_WINDOWS:
        return
    state = _saved_taskbar_state if _saved_taskbar_state is not None else ABS_ALWAYSONTOP
    _set_taskbar_state(state)
    for hwnd in _taskbar_windows():
        user32.ShowWindow(hwnd, SW_SHOW)
    _saved_taskbar_state = None


# --- foreground window queries ----------------------------------------------
def get_foreground_window() -> int:
    return int(user32.GetForegroundWindow() or 0) if IS_WINDOWS else 0


def get_class_name(hwnd: int) -> str:
    buf = ctypes.create_unicode_buffer(256)
    user32.GetClassNameW(hwnd, buf, 256)
    return buf.value


def get_window_title(hwnd: int) -> str:
    buf = ctypes.create_unicode_buffer(512)
    user32.GetWindowTextW(hwnd, buf, 512)
    return buf.value


def get_window_pid(hwnd: int) -> int:
    pid = wintypes.DWORD(0)
    user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
    return int(pid.value)


def window_command(hwnd: int, command: str) -> None:
    """command: 'minimize' | 'maximize' (toggles restore) | 'close'."""
    if not IS_WINDOWS or not hwnd:
        return
    if command == "minimize":
        sc = SC_MINIMIZE
    elif command == "maximize":
        sc = SC_RESTORE if user32.IsZoomed(hwnd) else SC_MAXIMIZE
    elif command == "close":
        sc = SC_CLOSE
    else:
        return
    user32.PostMessageW(hwnd, WM_SYSCOMMAND, sc, 0)


def is_maximized(hwnd: int) -> bool:
    return bool(IS_WINDOWS and hwnd and user32.IsZoomed(hwnd))


def lock_workstation() -> None:
    if IS_WINDOWS:
        user32.LockWorkStation()


# --- global hotkeys ---------------------------------------------------------
def register_hotkey(hotkey_id: int, modifiers: int, vk: int) -> bool:
    return bool(IS_WINDOWS and user32.RegisterHotKey(None, hotkey_id, modifiers, vk))


def unregister_hotkey(hotkey_id: int) -> None:
    if IS_WINDOWS:
        user32.UnregisterHotKey(None, hotkey_id)


# =============================================================================
# Phase 2: running-window enumeration, activation, recycle bin
# =============================================================================
GW_OWNER = 4
DWMWA_CLOAKED = 14
SW_RESTORE = 9
SHELL_CLASSES = {"Progman", "WorkerW", "Shell_TrayWnd", "Shell_SecondaryTrayWnd",
                 "Windows.UI.Core.CoreWindow"}


class SHQUERYRBINFO(ctypes.Structure):
    _fields_ = [
        ("cbSize", wintypes.DWORD),
        ("i64Size", ctypes.c_longlong),
        ("i64NumItems", ctypes.c_longlong),
    ]


if IS_WINDOWS:
    dwmapi = ctypes.WinDLL("dwmapi")
    kernel32 = ctypes.WinDLL("kernel32")
    WNDENUMPROC = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
    _sig(user32.EnumWindows, wintypes.BOOL, WNDENUMPROC, wintypes.LPARAM)
    _sig(user32.IsWindowVisible, wintypes.BOOL, wintypes.HWND)
    _sig(user32.IsIconic, wintypes.BOOL, wintypes.HWND)
    _sig(user32.GetWindow, wintypes.HWND, wintypes.HWND, wintypes.UINT)
    _sig(user32.GetWindowTextLengthW, ctypes.c_int, wintypes.HWND)
    _sig(user32.SetForegroundWindow, wintypes.BOOL, wintypes.HWND)
    _sig(user32.BringWindowToTop, wintypes.BOOL, wintypes.HWND)
    _sig(user32.AttachThreadInput, wintypes.BOOL, wintypes.DWORD, wintypes.DWORD, wintypes.BOOL)
    _sig(kernel32.GetCurrentThreadId, wintypes.DWORD)
    _sig(dwmapi.DwmGetWindowAttribute, ctypes.c_long, wintypes.HWND, wintypes.DWORD,
         ctypes.c_void_p, wintypes.DWORD)
    _sig(shell32.SHQueryRecycleBinW, ctypes.c_long, wintypes.LPCWSTR, ctypes.POINTER(SHQUERYRBINFO))
    _sig(shell32.SHEmptyRecycleBinW, ctypes.c_long, wintypes.HWND, wintypes.LPCWSTR, wintypes.DWORD)


def list_app_windows() -> list[int]:
    """Top-level windows that would appear in a taskbar, front-to-back (z-order)."""
    if not IS_WINDOWS:
        return []
    found: list[int] = []

    def _callback(hwnd, _lparam):
        try:
            if not user32.IsWindowVisible(hwnd):
                return True
            ex = user32.GetWindowLongPtrW(hwnd, GWL_EXSTYLE)
            is_appwindow = bool(ex & WS_EX_APPWINDOW)
            if (ex & WS_EX_TOOLWINDOW) and not is_appwindow:
                return True
            if user32.GetWindow(hwnd, GW_OWNER) and not is_appwindow:
                return True
            if user32.GetWindowTextLengthW(hwnd) == 0:
                return True
            cloaked = wintypes.DWORD(0)  # hidden UWP shells report as "cloaked"
            dwmapi.DwmGetWindowAttribute(hwnd, DWMWA_CLOAKED, ctypes.byref(cloaked),
                                         ctypes.sizeof(cloaked))
            if cloaked.value:
                return True
            if get_class_name(hwnd) in SHELL_CLASSES:
                return True
            found.append(int(hwnd))
        except Exception:
            pass
        return True

    callback = WNDENUMPROC(_callback)  # keep a reference while EnumWindows runs
    user32.EnumWindows(callback, 0)
    return found


def activate_window(hwnd: int) -> None:
    """Restore (if minimized) and bring a window to the foreground."""
    if not IS_WINDOWS or not hwnd:
        return
    if user32.IsIconic(hwnd):
        user32.ShowWindow(hwnd, SW_RESTORE)
    # Windows only lets the foreground thread change focus; briefly share its input queue.
    fg = user32.GetForegroundWindow()
    fg_thread = user32.GetWindowThreadProcessId(fg, None) if fg else 0
    this_thread = kernel32.GetCurrentThreadId()
    attached = bool(fg_thread and fg_thread != this_thread
                    and user32.AttachThreadInput(this_thread, fg_thread, True))
    user32.BringWindowToTop(hwnd)
    user32.SetForegroundWindow(hwnd)
    if attached:
        user32.AttachThreadInput(this_thread, fg_thread, False)


def recycle_bin_items() -> int:
    """Number of items in the Recycle Bin (0 on error / non-Windows)."""
    if not IS_WINDOWS:
        return 0
    info = SHQUERYRBINFO()
    info.cbSize = ctypes.sizeof(SHQUERYRBINFO)
    if shell32.SHQueryRecycleBinW(None, ctypes.byref(info)) != 0:
        return 0
    return int(info.i64NumItems)


def empty_recycle_bin() -> None:
    if IS_WINDOWS:
        shell32.SHEmptyRecycleBinW(None, None, 0)  # 0 = normal confirmation dialog


# =============================================================================
# Phase 3-5: z-order, media keys, Windows light/dark mode
# =============================================================================
HWND_BOTTOM = 1
HWND_NOTOPMOST = -2
KEYEVENTF_EXTENDEDKEY, KEYEVENTF_KEYUP = 0x0001, 0x0002
VK_MEDIA_NEXT, VK_MEDIA_PREV, VK_MEDIA_PLAY_PAUSE = 0xB0, 0xB1, 0xB3
PERSONALIZE_KEY = r"Software\Microsoft\Windows\CurrentVersion\Themes\Personalize"

if IS_WINDOWS:
    _sig(user32.keybd_event, None, wintypes.BYTE, wintypes.BYTE, wintypes.DWORD, ctypes.c_size_t)
    _sig(user32.SendMessageTimeoutW, ctypes.c_ssize_t, wintypes.HWND, wintypes.UINT, wintypes.WPARAM,
         wintypes.LPCWSTR, wintypes.UINT, wintypes.UINT, ctypes.POINTER(ctypes.c_size_t))


def set_window_z(hwnd: int, where: str) -> None:
    """where: 'bottom' (desktop layer) | 'top' (always on top) | 'normal'."""
    if not IS_WINDOWS:
        return
    insert_after = {"bottom": HWND_BOTTOM, "top": HWND_TOPMOST, "normal": HWND_NOTOPMOST}[where]
    user32.SetWindowPos(hwnd, wintypes.HWND(insert_after), 0, 0, 0, 0,
                        SWP_NOMOVE | SWP_NOSIZE | SWP_NOACTIVATE)


def send_media_key(vk: int) -> None:
    if not IS_WINDOWS:
        return
    user32.keybd_event(vk, 0, KEYEVENTF_EXTENDEDKEY, 0)
    user32.keybd_event(vk, 0, KEYEVENTF_EXTENDEDKEY | KEYEVENTF_KEYUP, 0)


def get_windows_dark_mode() -> bool:
    if not IS_WINDOWS:
        return True
    import winreg
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, PERSONALIZE_KEY) as key:
            return winreg.QueryValueEx(key, "AppsUseLightTheme")[0] == 0
    except OSError:
        return False


def set_windows_dark_mode(dark: bool) -> None:
    """Switch Windows' own app + system theme (no admin needed)."""
    if not IS_WINDOWS:
        return
    import winreg
    value = 0 if dark else 1
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, PERSONALIZE_KEY, 0, winreg.KEY_SET_VALUE) as key:
            winreg.SetValueEx(key, "AppsUseLightTheme", 0, winreg.REG_DWORD, value)
            winreg.SetValueEx(key, "SystemUsesLightTheme", 0, winreg.REG_DWORD, value)
    except OSError:
        return
    result = ctypes.c_size_t(0)   # tell running apps the theme changed
    user32.SendMessageTimeoutW(wintypes.HWND(0xFFFF), 0x001A, 0, "ImmersiveColorSet", 2, 200,
                               ctypes.byref(result))


# =============================================================================
# v4: window rects, desktop icons, DWM title-bar styling
# =============================================================================
DWMWA_USE_IMMERSIVE_DARK_MODE = 20
DWMWA_WINDOW_CORNER_PREFERENCE = 33
DWMWA_BORDER_COLOR, DWMWA_CAPTION_COLOR, DWMWA_TEXT_COLOR = 34, 35, 36
DWMWCP_ROUND = 2
DWM_COLOR_DEFAULT = 0xFFFFFFFF

if IS_WINDOWS:
    _sig(user32.GetWindowRect, wintypes.BOOL, wintypes.HWND, ctypes.POINTER(wintypes.RECT))
    _sig(dwmapi.DwmSetWindowAttribute, ctypes.c_long, wintypes.HWND, wintypes.DWORD,
         ctypes.c_void_p, wintypes.DWORD)


def get_window_rect(hwnd: int) -> tuple[int, int, int, int] | None:
    """(left, top, right, bottom) in physical pixels."""
    if not IS_WINDOWS:
        return None
    rc = wintypes.RECT()
    if not user32.GetWindowRect(hwnd, ctypes.byref(rc)):
        return None
    return rc.left, rc.top, rc.right, rc.bottom


def is_minimized(hwnd: int) -> bool:
    return bool(IS_WINDOWS and user32.IsIconic(hwnd))


def _desktop_listview() -> int | None:
    progman = user32.FindWindowW("Progman", None)
    defview = user32.FindWindowExW(progman, None, "SHELLDLL_DefView", None) if progman else None
    if not defview:
        worker = None
        while True:  # on some builds the icons live under a WorkerW window
            worker = user32.FindWindowExW(None, worker, "WorkerW", None)
            if not worker:
                break
            defview = user32.FindWindowExW(worker, None, "SHELLDLL_DefView", None)
            if defview:
                break
    return user32.FindWindowExW(defview, None, "SysListView32", None) if defview else None


def set_desktop_icons_visible(visible: bool) -> None:
    if not IS_WINDOWS:
        return
    listview = _desktop_listview()
    if listview:
        user32.ShowWindow(listview, SW_SHOW if visible else SW_HIDE)


def _rgb_to_colorref(rgb: tuple[int, int, int]) -> int:
    r, g, b = rgb
    return (b << 16) | (g << 8) | r


def _dwm_set(hwnd: int, attribute: int, value: int) -> None:
    v = ctypes.c_uint(value & 0xFFFFFFFF)
    dwmapi.DwmSetWindowAttribute(hwnd, attribute, ctypes.byref(v), ctypes.sizeof(v))


def style_titlebar(hwnd: int, caption: tuple[int, int, int], text: tuple[int, int, int], dark: bool) -> None:
    """Windows 11: recolor another window's title bar and border (silently ignored elsewhere)."""
    if not IS_WINDOWS:
        return
    try:
        _dwm_set(hwnd, DWMWA_USE_IMMERSIVE_DARK_MODE, 1 if dark else 0)
        _dwm_set(hwnd, DWMWA_CAPTION_COLOR, _rgb_to_colorref(caption))
        _dwm_set(hwnd, DWMWA_BORDER_COLOR, _rgb_to_colorref(caption))
        _dwm_set(hwnd, DWMWA_TEXT_COLOR, _rgb_to_colorref(text))
        _dwm_set(hwnd, DWMWA_WINDOW_CORNER_PREFERENCE, DWMWCP_ROUND)
    except Exception:
        pass


def reset_titlebar(hwnd: int) -> None:
    if not IS_WINDOWS:
        return
    try:
        for attr in (DWMWA_CAPTION_COLOR, DWMWA_BORDER_COLOR, DWMWA_TEXT_COLOR):
            _dwm_set(hwnd, attr, DWM_COLOR_DEFAULT)
    except Exception:
        pass


# =============================================================================
# v5: keep the Windows taskbar gone, brief taskbar peek for the system tray
# =============================================================================
def taskbar_visible() -> bool:
    return bool(IS_WINDOWS and any(user32.IsWindowVisible(h) for h in _taskbar_windows()))


def enforce_taskbar_hidden() -> None:
    """Explorer re-shows the taskbar on some events (Win key, notifications, restarts); hide it again."""
    if not IS_WINDOWS:
        return
    windows = _taskbar_windows()
    if any(user32.IsWindowVisible(h) for h in windows):
        _set_taskbar_state(ABS_AUTOHIDE)
        for hwnd in windows:
            user32.ShowWindow(hwnd, SW_HIDE)


def show_taskbar_for_tray() -> None:
    """Show the real taskbar so its notification area (tray icons, clock flyout) is reachable."""
    if not IS_WINDOWS:
        return
    for hwnd in _taskbar_windows():
        user32.ShowWindow(hwnd, SW_SHOW)
        user32.SetWindowPos(hwnd, wintypes.HWND(HWND_TOPMOST), 0, 0, 0, 0,
                            SWP_NOMOVE | SWP_NOSIZE | SWP_NOACTIVATE)


def cursor_over_taskbar() -> bool:
    if not IS_WINDOWS:
        return False
    pt = wintypes.POINT()
    ctypes.windll.user32.GetCursorPos(ctypes.byref(pt))
    for hwnd in _taskbar_windows():
        rc = wintypes.RECT()
        if user32.GetWindowRect(hwnd, ctypes.byref(rc)) and rc.left <= pt.x <= rc.right and rc.top <= pt.y <= rc.bottom:
            return True
    return False
