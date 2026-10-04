"""Detect whether we run as an MSIX/Store package (then the Store handles install, update and startup)."""
from __future__ import annotations

import ctypes
import sys

from . import winapi


def is_packaged() -> bool:
    if not winapi.IS_WINDOWS:
        return False
    try:
        kernel32 = winapi._dll("kernel32")
        length = ctypes.c_uint32(0)
        # APPMODEL_ERROR_NO_PACKAGE (15700) when not packaged; ERROR_INSUFFICIENT_BUFFER (122) when packaged
        return kernel32.GetCurrentPackageFullName(ctypes.byref(length), None) != 15700
    except Exception:
        return False


def edition() -> str:
    return "store" if is_packaged() else ("installer" if getattr(sys, "frozen", False) else "source")
