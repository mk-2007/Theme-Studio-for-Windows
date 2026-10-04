"""Crash safety net: a tiny second process that puts the Windows taskbar back if Theme Studio dies,
plus crash detection so the next start can come up in safe mode."""
from __future__ import annotations

import os
import subprocess
import sys

from . import winapi
from .settings import settings_dir

CREATE_NO_WINDOW, DETACHED_PROCESS = 0x08000000, 0x00000008
SYNCHRONIZE, PROCESS_QUERY_LIMITED_INFORMATION = 0x00100000, 0x1000
STILL_ACTIVE = 259


def _flag():
    return settings_dir() / "running.flag"


def pid_alive(pid: int) -> bool:
    if pid <= 0:
        return False
    if not winapi.IS_WINDOWS:
        try:
            os.kill(pid, 0)
            return True
        except OSError:
            return False
    import ctypes
    from ctypes import wintypes
    kernel32 = winapi._dll("kernel32")
    kernel32.OpenProcess.restype = ctypes.c_void_p
    handle = kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
    if not handle:
        return False
    try:
        code = wintypes.DWORD()
        return bool(kernel32.GetExitCodeProcess(ctypes.c_void_p(handle), ctypes.byref(code))) and code.value == STILL_ACTIVE
    finally:
        kernel32.CloseHandle(ctypes.c_void_p(handle))


def previous_run_crashed() -> bool:
    """True when the last session left its marker behind and that process is gone (crash, kill, power loss)."""
    try:
        pid = int(_flag().read_text().strip())
    except (OSError, ValueError):
        return False
    return pid != os.getpid() and not pid_alive(pid)


def mark_running() -> None:
    try:
        _flag().write_text(str(os.getpid()))
    except OSError:
        pass


def mark_clean() -> None:
    try:
        _flag().unlink()
    except OSError:
        pass


def spawn_guard() -> None:
    if not winapi.IS_WINDOWS:
        return
    cmd = [sys.executable]
    if not getattr(sys, "frozen", False):
        cmd.append(os.path.abspath(sys.argv[0]))
    cmd += ["--guard", str(os.getpid())]
    try:
        subprocess.Popen(cmd, creationflags=CREATE_NO_WINDOW | DETACHED_PROCESS, close_fds=True,
                         stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except OSError as exc:
        print(f"[guard] could not start: {exc}")


def wait_for_pid(pid: int, timeout_ms: int = 0xFFFFFFFF) -> None:
    if not winapi.IS_WINDOWS or pid <= 0:
        return
    import ctypes
    kernel32 = winapi._dll("kernel32")
    kernel32.OpenProcess.restype = ctypes.c_void_p
    handle = kernel32.OpenProcess(SYNCHRONIZE, False, pid)
    if handle:
        kernel32.WaitForSingleObject(ctypes.c_void_p(handle), timeout_ms)
        kernel32.CloseHandle(ctypes.c_void_p(handle))


def run_guard(pid: int) -> int:
    """Runs in the guard process: wait for the app to exit, and if it did not exit cleanly, restore Windows."""
    wait_for_pid(pid)
    if _flag().exists():
        winapi.restore_taskbar()
        winapi.set_desktop_icons_visible(True)
        mark_clean()
    return 0
