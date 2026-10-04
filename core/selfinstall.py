"""One-file sharing: ThemeStudio-Setup.exe installs itself on first run (no Python needed).

Security notes: no shell=True, no user-controlled text is ever pasted into a script (paths travel in environment
variables), the uninstall target must be exactly our own install folder, and nothing here runs for Store builds.
"""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

from . import packaged, syspath, winapi

CREATE_NO_WINDOW = 0x08000000
_RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
_PS = [syspath.tool("powershell"), "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass", "-Command"]


def install_dir() -> Path:
    base = os.environ.get("LOCALAPPDATA", "")
    if not base or not os.path.isabs(base):
        raise RuntimeError("LOCALAPPDATA is not set")
    return Path(base) / "Programs" / "ThemeStudio"


def installed_exe() -> Path:
    return install_dir() / "ThemeStudio.exe"


def is_frozen() -> bool:
    return bool(getattr(sys, "frozen", False)) and winapi.IS_WINDOWS


def running_from_install_dir() -> bool:
    try:
        return Path(sys.executable).resolve().parent == install_dir().resolve()
    except (OSError, RuntimeError):
        return False


def should_offer_install() -> bool:
    return is_frozen() and not running_from_install_dir() and not packaged.is_packaged()


def _shortcut_paths() -> tuple[Path, Path]:
    start = Path(os.environ["APPDATA"]) / "Microsoft" / "Windows" / "Start Menu" / "Programs" / "Theme Studio.lnk"
    desktop = Path(os.environ.get("USERPROFILE", str(Path.home()))) / "Desktop" / "Theme Studio.lnk"
    return start, desktop


def _run_ps(script: str, env_extra: dict[str, str]) -> None:
    env = dict(os.environ, **env_extra)
    subprocess.run(_PS + [script], creationflags=CREATE_NO_WINDOW, timeout=30, check=False, env=env,
                   stdin=subprocess.DEVNULL, capture_output=True)


def is_safe_install_target(path: Path) -> bool:
    """We only ever delete a folder named ThemeStudio inside <LocalAppData>\\Programs."""
    try:
        resolved = path.resolve()
        expected = install_dir().resolve()
    except (OSError, RuntimeError):
        return False
    return resolved == expected and resolved.name == "ThemeStudio" and resolved.parent.name == "Programs" \
        and len(resolved.parts) >= 4


def install() -> Path:
    """Copy this exe into the user's programs folder, add shortcuts + startup, return the installed exe."""
    if packaged.is_packaged():
        raise RuntimeError("Store builds are installed by the Store")
    dest, exe = install_dir(), installed_exe()
    subprocess.run([syspath.tool("taskkill"), "/IM", "ThemeStudio.exe", "/F", "/FI", f"USERNAME eq {os.environ.get('USERNAME', '')}"],
                   creationflags=CREATE_NO_WINDOW, capture_output=True, check=False)
    dest.mkdir(parents=True, exist_ok=True)
    for _attempt in range(10):
        try:
            shutil.copy2(sys.executable, exe)
            break
        except PermissionError:                                  # old copy still shutting down
            time.sleep(0.5)
    else:
        raise PermissionError("Could not replace the installed copy")

    start, desktop = _shortcut_paths()
    script = ("$ws = New-Object -ComObject WScript.Shell; "
              "foreach ($p in @($env:TS_LNK1, $env:TS_LNK2)) { "
              "$l = $ws.CreateShortcut($p); $l.TargetPath = $env:TS_EXE; $l.WorkingDirectory = $env:TS_DIR; "
              "$l.IconLocation = $env:TS_EXE; $l.Description = 'Theme Studio'; $l.Save() }")
    _run_ps(script, {"TS_LNK1": str(start), "TS_LNK2": str(desktop), "TS_EXE": str(exe), "TS_DIR": str(dest)})

    import winreg
    with winreg.OpenKey(winreg.HKEY_CURRENT_USER, _RUN_KEY, 0, winreg.KEY_SET_VALUE) as key:
        winreg.SetValueEx(key, "ThemeStudio", 0, winreg.REG_SZ, f'"{exe}"')
    return exe


def launch(exe: Path) -> None:
    subprocess.Popen([str(exe)], cwd=str(exe.parent), creationflags=CREATE_NO_WINDOW, close_fds=True)


def uninstall() -> None:
    """Remove shortcuts and the startup entry, then delete the install folder after this process exits."""
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
    target = install_dir()
    if running_from_install_dir() and is_safe_install_target(target):
        script = "Start-Sleep -Seconds 3; Remove-Item -LiteralPath $env:TS_DIR -Recurse -Force -ErrorAction SilentlyContinue"
        env = dict(os.environ, TS_DIR=str(target))
        subprocess.Popen(_PS + [script], creationflags=CREATE_NO_WINDOW | 0x00000008, env=env,
                         stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, close_fds=True)
