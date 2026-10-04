"""System information and actions: foreground app, battery, power, settings."""
from __future__ import annotations

import os
import subprocess

import psutil

from . import syspath, winapi

CREATE_NO_WINDOW = 0x08000000

_SHELL_CLASSES = {"Progman", "WorkerW", "Shell_TrayWnd", "Shell_SecondaryTrayWnd"}

_FRIENDLY = {
    "chrome": "Google Chrome", "msedge": "Microsoft Edge", "firefox": "Firefox",
    "brave": "Brave", "opera": "Opera", "code": "VS Code", "cursor": "Cursor",
    "devenv": "Visual Studio", "pycharm64": "PyCharm", "idea64": "IntelliJ IDEA",
    "explorer": "File Explorer", "notepad": "Notepad", "windowsterminal": "Terminal",
    "cmd": "Command Prompt", "powershell": "PowerShell", "pwsh": "PowerShell",
    "winword": "Word", "excel": "Excel", "powerpnt": "PowerPoint", "outlook": "Outlook",
    "spotify": "Spotify", "discord": "Discord", "whatsapp": "WhatsApp",
    "slack": "Slack", "teams": "Teams", "ms-teams": "Teams", "zoom": "Zoom",
    "obs64": "OBS Studio", "vlc": "VLC", "taskmgr": "Task Manager",
    "systemsettings": "Settings", "python": "Python", "pythonw": "Python",
}


def _pretty(process_name: str) -> str:
    stem = process_name.rsplit(".", 1)[0] if process_name.lower().endswith(".exe") else process_name
    key = stem.lower()
    if key in _FRIENDLY:
        return _FRIENDLY[key]
    words = stem.replace("-", " ").replace("_", " ")
    return words.title() if words.islower() else words


def foreground_app() -> tuple[int, str] | None:
    """(hwnd, display name) of the focused app.

    hwnd is 0 for the desktop/shell. Returns None when Theme Studio itself has
    focus, so callers keep showing the last real app.
    """
    if not winapi.IS_WINDOWS:
        return None
    hwnd = winapi.get_foreground_window()
    if not hwnd or winapi.get_class_name(hwnd) in _SHELL_CLASSES:
        return 0, "Desktop"
    pid = winapi.get_window_pid(hwnd)
    if pid == os.getpid():
        return None
    try:
        name = psutil.Process(pid).name()
    except (psutil.Error, OSError):
        return hwnd, winapi.get_window_title(hwnd) or "Unknown"
    if name.lower() == "applicationframehost.exe":  # UWP apps live behind this host
        return hwnd, winapi.get_window_title(hwnd) or "App"
    return hwnd, _pretty(name)


def battery() -> tuple[int, bool] | None:
    """(percent, plugged_in) or None on machines without a battery."""
    try:
        info = psutil.sensors_battery()
    except Exception:
        return None
    if info is None:
        return None
    return int(info.percent), bool(info.power_plugged)


def _run(args: list[str]) -> None:
    flags = CREATE_NO_WINDOW if winapi.IS_WINDOWS else 0
    subprocess.Popen(args, creationflags=flags)


def lock_screen() -> None:
    winapi.lock_workstation()


def sleep() -> None:
    _run([syspath.tool("rundll32"), "powrprof.dll,SetSuspendState", "0,1,0"])


def restart() -> None:
    _run([syspath.tool("shutdown"), "/r", "/t", "0"])


def shutdown() -> None:
    _run([syspath.tool("shutdown"), "/s", "/t", "0"])


def open_system_settings() -> None:
    if winapi.IS_WINDOWS:
        os.startfile("ms-settings:")  # type: ignore[attr-defined]


def open_task_manager() -> None:
    _run([syspath.tool("taskmgr")])


pretty_name = _pretty  # public alias used by the dock


# ---------------------------------------------------------------- Phase 3-6 helpers
_ALLOWED_URI_PREFIXES = ("https://", "ms-settings:", "shell:recyclebinfolder")


def is_allowed_uri(uri: object) -> bool:
    """Only a short allow-list of schemes may be opened (no file:, javascript:, search-ms:, custom handlers...)."""
    if not isinstance(uri, str) or not uri or len(uri) > 2000 or any(ord(c) < 32 for c in uri):
        return False
    low = uri.lower()
    if low.startswith(_ALLOWED_URI_PREFIXES):
        return True
    return os.path.isabs(uri) and os.path.exists(uri)          # an existing local path (e.g. the log file)


def open_uri(uri: str) -> None:
    """Open a settings page / https URL / local path with the default handler."""
    if not is_allowed_uri(uri):
        print("[system] refused to open a disallowed URI")
        return
    try:
        if winapi.IS_WINDOWS:
            os.startfile(uri)  # type: ignore[attr-defined]
        else:
            import webbrowser
            webbrowser.open(uri)
    except OSError as exc:
        print(f"[system] could not open URI: {exc}")


def wifi_ssid() -> str | None:
    """Name of the connected Wi-Fi network (blocking, ~100 ms; call from a thread)."""
    if not winapi.IS_WINDOWS:
        return None
    try:
        out = subprocess.run([syspath.tool("netsh"), "wlan", "show", "interfaces"], capture_output=True,
                             text=True, timeout=3, creationflags=CREATE_NO_WINDOW).stdout
    except Exception:
        return None
    for line in out.splitlines():
        line = line.strip()
        if line.startswith("SSID") and not line.startswith("BSSID"):
            value = line.partition(":")[2].strip()
            return value or None
    return None


_RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
_RUN_NAME = "ThemeStudio"


def _startup_command(hide_taskbar: bool) -> str:
    import sys
    exe = sys.executable
    if getattr(sys, "frozen", False):
        cmd = f'"{exe}"'
    else:
        pyw = os.path.join(os.path.dirname(exe), "pythonw.exe")
        cmd = f'"{pyw if os.path.exists(pyw) else exe}" "{os.path.abspath(sys.argv[0])}"'
    return cmd + (" --hide-taskbar" if hide_taskbar else "")


def autostart_enabled() -> bool:
    if not winapi.IS_WINDOWS:
        return False
    import winreg
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, _RUN_KEY) as key:
            winreg.QueryValueEx(key, _RUN_NAME)
            return True
    except OSError:
        return False


def set_autostart(enabled: bool, hide_taskbar: bool = False) -> None:
    if not winapi.IS_WINDOWS:
        return
    import winreg
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, _RUN_KEY, 0, winreg.KEY_SET_VALUE) as key:
            if enabled:
                winreg.SetValueEx(key, _RUN_NAME, 0, winreg.REG_SZ, _startup_command(hide_taskbar))
            else:
                try:
                    winreg.DeleteValue(key, _RUN_NAME)
                except FileNotFoundError:
                    pass
    except OSError as exc:
        print(f"[autostart] failed: {exc}")
