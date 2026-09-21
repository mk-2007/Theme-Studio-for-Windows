"""Crisp app icons straight from the Windows shell (up to 256 px, with alpha).

Uses IShellItemImageFactory, which also works for Store apps ("shell:AppsFolder\\<AppID>").
Everything is optional: any failure returns None and callers fall back to Qt's icon provider.
"""
from __future__ import annotations

import ctypes
import sys
from ctypes import wintypes

from PyQt6.QtGui import QImage, QPixmap

IS_WINDOWS = sys.platform == "win32"
SIIGBF_ICONONLY = 0x4

if IS_WINDOWS:
    ole32 = ctypes.WinDLL("ole32")
    shell32 = ctypes.WinDLL("shell32")
    gdi32 = ctypes.WinDLL("gdi32")
    user32 = ctypes.WinDLL("user32")

    class GUID(ctypes.Structure):
        _fields_ = [("Data1", ctypes.c_ulong), ("Data2", ctypes.c_ushort),
                    ("Data3", ctypes.c_ushort), ("Data4", ctypes.c_ubyte * 8)]

    class SIZE(ctypes.Structure):
        _fields_ = [("cx", ctypes.c_long), ("cy", ctypes.c_long)]

    class BITMAP(ctypes.Structure):
        _fields_ = [("bmType", ctypes.c_long), ("bmWidth", ctypes.c_long), ("bmHeight", ctypes.c_long),
                    ("bmWidthBytes", ctypes.c_long), ("bmPlanes", wintypes.WORD),
                    ("bmBitsPixel", wintypes.WORD), ("bmBits", ctypes.c_void_p)]

    class BITMAPINFOHEADER(ctypes.Structure):
        _fields_ = [("biSize", wintypes.DWORD), ("biWidth", ctypes.c_long), ("biHeight", ctypes.c_long),
                    ("biPlanes", wintypes.WORD), ("biBitCount", wintypes.WORD),
                    ("biCompression", wintypes.DWORD), ("biSizeImage", wintypes.DWORD),
                    ("biXPelsPerMeter", ctypes.c_long), ("biYPelsPerMeter", ctypes.c_long),
                    ("biClrUsed", wintypes.DWORD), ("biClrImportant", wintypes.DWORD)]

    ole32.CLSIDFromString.argtypes = [wintypes.LPCWSTR, ctypes.POINTER(GUID)]
    shell32.SHCreateItemFromParsingName.argtypes = [wintypes.LPCWSTR, ctypes.c_void_p,
                                                    ctypes.POINTER(GUID), ctypes.POINTER(ctypes.c_void_p)]
    shell32.SHCreateItemFromParsingName.restype = ctypes.c_long
    gdi32.GetObjectW.argtypes = [ctypes.c_void_p, ctypes.c_int, ctypes.c_void_p]
    gdi32.GetDIBits.argtypes = [ctypes.c_void_p, ctypes.c_void_p, wintypes.UINT, wintypes.UINT,
                                ctypes.c_void_p, ctypes.c_void_p, wintypes.UINT]
    gdi32.DeleteObject.argtypes = [ctypes.c_void_p]
    user32.GetDC.argtypes = [ctypes.c_void_p]
    user32.GetDC.restype = ctypes.c_void_p
    user32.ReleaseDC.argtypes = [ctypes.c_void_p, ctypes.c_void_p]

    _IID = GUID()
    ole32.CLSIDFromString("{BCC18B79-BA16-442F-80C4-8A59C30C463B}", ctypes.byref(_IID))
    _GETIMAGE = ctypes.WINFUNCTYPE(ctypes.c_long, ctypes.c_void_p, SIZE, ctypes.c_uint,
                                   ctypes.POINTER(ctypes.c_void_p))
    _RELEASE = ctypes.WINFUNCTYPE(ctypes.c_ulong, ctypes.c_void_p)


def _hbitmap_to_image(hbm: int) -> QImage | None:
    bm = BITMAP()
    if not gdi32.GetObjectW(hbm, ctypes.sizeof(BITMAP), ctypes.byref(bm)):
        return None
    w, h = bm.bmWidth, abs(bm.bmHeight)
    if w <= 0 or h <= 0:
        return None
    header = BITMAPINFOHEADER()
    header.biSize = ctypes.sizeof(BITMAPINFOHEADER)
    header.biWidth, header.biHeight = w, -h            # negative = top-down
    header.biPlanes, header.biBitCount = 1, 32
    buf = (ctypes.c_ubyte * (w * h * 4))()
    hdc = user32.GetDC(None)
    try:
        lines = gdi32.GetDIBits(hdc, hbm, 0, h, buf, ctypes.byref(header), 0)
    finally:
        user32.ReleaseDC(None, hdc)
    if not lines:
        return None
    img = QImage(bytes(buf), w, h, w * 4, QImage.Format.Format_ARGB32_Premultiplied).copy()
    # some shell bitmaps carry no alpha at all; treat those as opaque
    if all(img.pixelColor(x, y).alpha() == 0 for x in range(w // 2 - 2, w // 2 + 2) for y in range(h // 2 - 2, h // 2 + 2)):
        img = img.convertToFormat(QImage.Format.Format_RGB32)
    return img


def icon_pixmap(path: str, size: int = 256) -> QPixmap | None:
    if not IS_WINDOWS or not path:
        return None
    try:
        item = ctypes.c_void_p()
        if shell32.SHCreateItemFromParsingName(path, None, ctypes.byref(_IID), ctypes.byref(item)) != 0 or not item:
            return None
        vtable = ctypes.cast(item, ctypes.POINTER(ctypes.POINTER(ctypes.c_void_p)))[0]
        get_image = _GETIMAGE(vtable[3])
        release = _RELEASE(vtable[2])
        hbm = ctypes.c_void_p()
        try:
            hr = get_image(item, SIZE(size, size), SIIGBF_ICONONLY, ctypes.byref(hbm))
            if hr != 0 or not hbm:
                return None
            try:
                img = _hbitmap_to_image(hbm.value)
            finally:
                gdi32.DeleteObject(hbm.value)
        finally:
            release(item)
        return QPixmap.fromImage(img) if img is not None else None
    except Exception:
        return None
