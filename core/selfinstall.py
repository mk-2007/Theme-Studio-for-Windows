"""One-file sharing: ThemeStudio-Setup.exe installs itself on first run (no Python needed)."""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

from . import winapi

CREATE_NO_WINDOW = 0x08000000
_RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"


def install_dir() -> Path:
    return Path(os.environ.get("LOCALAPPDATA", str(Path.home()))) / "Programs" / "ThemeStudio"


def installed_exe() -> Path:
    return install_dir() / "ThemeStudio.exe"


def is_frozen() -> bool:
    return bool(getattr(sys, "frozen", False)) and winapi.IS_WINDOWS


def running_from_install_dir() -> bool:
    try:
        return Path(sys.executable).resolve().parent == install_dir().resolve()
    except OSError:
        return False


def should_offer_install() -> bool:
    return is_frozen() and not running_from_install_dir()


def _ps(script: str) -> None:
    subprocess.run(["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", script],
                   creationflags=CREATE_NO_WINDOW, timeout=30, check=False)


def _shortcut_paths() -> tuple[Path, Path]:
    start = Path(os.environ["APPDATA"]) / "Microsoft" / "Windows" / "Start Menu" / "Programs" / "Theme Studio.lnk"
    desktop = Path(os.environ.get("USERPROFILE", str(Path.home()))) / "Desktop" / "Theme Studio.lnk"
    return start, desktop


def install() -> Path:
    """Copy this exe into the user's programs folder, add shortcuts + startup, return the installed exe."""
    dest = install_dir()
    exe = installed_exe()
    subprocess.run(["taskkill", "/IM", "ThemeStudio.exe", "/F"], creationflags=CREATE_NO_WINDOW,
                   capture_output=True, check=False)              # stop an older installed copy
    dest.mkdir(parents=True, exist_ok=True)
    for _attempt in range(10):
        try:
            shutil.copy2(sys.executable, exe)
            break
        except PermissionError:                                  # old copy still shutting down
            import time
            time.sleep(0.5)
    else:
        raise PermissionError(f"Could not replace {exe}")

    parts = []
    for lnk in _shortcut_paths():
        parts.append(f"$l = $ws.CreateShortcut('{lnk}'); $l.TargetPath = '{exe}'; "
                     f"$l.WorkingDirectory = '{dest}'; $l.IconLocation = '{exe}'; "
                     f"$l.Description = 'Theme Studio'; $l.Save();")
    _ps("$ws = New-Object -ComObject WScript.Shell; " + " ".join(parts))

    import winreg
    with winreg.OpenKey(winreg.HKEY_CURRENT_USER, _RUN_KEY, 0, winreg.KEY_SET_VALUE) as key:
        winreg.SetValueEx(key, "ThemeStudio", 0, winreg.REG_SZ, f'"{exe}"')
    return exe


def launch(exe: Path) -> None:
    subprocess.Popen([str(exe)], cwd=str(exe.parent), creationflags=CREATE_NO_WINDOW)


def uninstall() -> None:
    """Remove shortcuts and startup entry, then delete the install folder after this process exits."""
    import winreg
    for lnk in _shortcut_paths():
        try:
            lnk.unlink()
        except OSError:
            pass
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, _RUN_KEY, 0, winreg.KEY_SET_VALUE) as key:
            winreg.DeleteValue(key, "ThemeStudio")
    except OSError:
        pass
    if running_from_install_dir():
        subprocess.Popen(f'cmd /c ping -n 4 127.0.0.1 >nul & rmdir /s /q "{install_dir()}"',
                         creationflags=CREATE_NO_WINDOW, shell=True)
