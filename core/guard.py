"""Crash safety net: a tiny second process that puts the Windows taskbar back if Theme Studio dies."""
from __future__ import annotations

import os
import subprocess
import sys

from . import winapi
from .settings import settings_dir

CREATE_NO_WINDOW, DETACHED_PROCESS = 0x08000000, 0x00000008
SYNCHRONIZE = 0x00100000


def _flag():
    return settings_dir() / "running.flag"


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


def wait_for_pid(pid: int) -> None:
    if not winapi.IS_WINDOWS:
        return
    import ctypes
    kernel32 = ctypes.WinDLL("kernel32")
    kernel32.OpenProcess.restype = ctypes.c_void_p
    handle = kernel32.OpenProcess(SYNCHRONIZE, False, pid)
    if handle:
        kernel32.WaitForSingleObject(ctypes.c_void_p(handle), 0xFFFFFFFF)
        kernel32.CloseHandle(ctypes.c_void_p(handle))


def run_guard(pid: int) -> int:
    """Runs in the guard process: wait for the app to exit, and if it did not exit cleanly, restore Windows."""
    wait_for_pid(pid)
    if _flag().exists():
        winapi.restore_taskbar()
        winapi.set_desktop_icons_visible(True)
        mark_clean()
    return 0
