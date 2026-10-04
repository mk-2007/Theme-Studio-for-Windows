"""Absolute paths to trusted Windows system executables.

Building the full path (instead of relying on PATH to find "netsh", "powershell", ...) closes a classic
PATH-hijacking hole: a malicious "netsh.exe" placed earlier on PATH, or in the current directory, can never be
picked up instead of the real one. Every subprocess call in this app that starts a stock Windows tool goes
through here.
"""
from __future__ import annotations

import os
from pathlib import Path

from . import winapi

_SYSTEM_ROOT = os.environ.get("SystemRoot", r"C:\Windows")
_SYS32 = Path(_SYSTEM_ROOT) / "System32"

_TOOLS = {
    "taskkill": _SYS32 / "taskkill.exe",
    "netsh": _SYS32 / "netsh.exe",
    "powershell": _SYS32 / "WindowsPowerShell" / "v1.0" / "powershell.exe",
    "taskmgr": _SYS32 / "Taskmgr.exe",
    "rundll32": _SYS32 / "rundll32.exe",
    "shutdown": _SYS32 / "shutdown.exe",
    "explorer": Path(_SYSTEM_ROOT) / "explorer.exe",
}


def tool(name: str) -> str:
    """Absolute path to a known system tool. Falls back to the bare name only off Windows (tests/preview)."""
    path = _TOOLS.get(name)
    if path is not None and winapi.IS_WINDOWS and path.exists():
        return str(path)
    return name
