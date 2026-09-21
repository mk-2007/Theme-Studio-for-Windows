"""Logging for a windowless app: stdout/stderr and crashes go to a log file."""
from __future__ import annotations

import sys
import threading
import traceback
from datetime import datetime

from .settings import settings_dir


def log_path():
    return settings_dir() / "theme-studio.log"


def setup() -> None:
    path = log_path()
    try:
        if path.exists() and path.stat().st_size > 1_000_000:
            path.replace(path.with_suffix(".old.log"))
    except OSError:
        pass
    if getattr(sys, "frozen", False) or sys.stdout is None or sys.stderr is None or not sys.stdout.isatty():
        try:
            stream = open(path, "a", buffering=1, encoding="utf-8")
            sys.stdout = sys.stderr = stream
        except OSError:
            return
    print(f"\n===== Theme Studio started {datetime.now():%Y-%m-%d %H:%M:%S} =====")

    def hook(exc_type, exc, tb) -> None:
        print("".join(traceback.format_exception(exc_type, exc, tb)))

    sys.excepthook = hook
    threading.excepthook = lambda a: hook(a.exc_type, a.exc_value, a.exc_traceback)
    try:
        from PyQt6.QtCore import qInstallMessageHandler
        qInstallMessageHandler(lambda _mode, _ctx, msg: print(f"[qt] {msg}") if "propagateSizeHints" not in msg else None)
    except Exception:
        pass
