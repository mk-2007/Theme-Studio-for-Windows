"""Settings store: %APPDATA%/ThemeStudio/settings.json with strict validation.

Everything read from disk is untrusted (another program, a hand edit or corruption could change it), so each key
has a validator. Invalid or unknown values are dropped and the default is used instead; the app never crashes on a
bad settings file. Writes are atomic (temp file + replace).
"""
from __future__ import annotations

import json
import math
import os
from pathlib import Path
from typing import Any, Callable

from PyQt6.QtCore import QObject, pyqtSignal

MAX_FILE_BYTES = 1_000_000
MODES = ("macos", "ubuntu")
WIDGET_IDS = ("weather", "clock", "system", "calendar", "notes")


def settings_dir() -> Path:
    base = os.environ.get("APPDATA") or str(Path.home() / ".config")
    path = Path(base) / "ThemeStudio"
    path.mkdir(parents=True, exist_ok=True)
    return path


# ------------------------------------------------------------------ validators (return the value or raise ValueError)
def _theme_id(v):
    if isinstance(v, str) and 1 <= len(v) <= 40 and all(c.islower() or c.isdigit() or c == "_" for c in v):
        return v
    raise ValueError


def _bool(v):
    if isinstance(v, bool):
        return v
    raise ValueError


def _int(lo: int, hi: int) -> Callable:
    def check(v):
        if isinstance(v, int) and not isinstance(v, bool) and lo <= v <= hi:
            return v
        raise ValueError
    return check


def _choice(*options) -> Callable:
    def check(v):
        if isinstance(v, str) and v in options:
            return v
        raise ValueError
    return check


def _one_of_ints(*options) -> Callable:
    def check(v):
        if isinstance(v, int) and not isinstance(v, bool) and v in options:
            return v
        raise ValueError
    return check


def _str(maxlen: int) -> Callable:
    def check(v):
        if isinstance(v, str) and len(v) <= maxlen and "\x00" not in v:
            return v
        raise ValueError
    return check


def _hex_color_or_none(v):
    if v is None:
        return None
    if isinstance(v, str) and len(v) == 7 and v[0] == "#" and all(c in "0123456789abcdefABCDEF" for c in v[1:]):
        return v.lower()
    raise ValueError


def _pins(v):
    if not isinstance(v, list) or len(v) > 60:
        raise ValueError
    out = []
    for e in v:
        if not isinstance(e, dict):
            continue
        name, exe, launch = e.get("name"), e.get("exe", ""), e.get("launch", "")
        if not (isinstance(name, str) and isinstance(exe, str) and isinstance(launch, str)):
            continue
        if not name or len(name) > 120 or len(exe) > 1024 or len(launch) > 1024:
            continue
        if "\x00" in name + exe + launch or not (exe or launch):
            continue
        out.append({"name": name, "exe": exe, "launch": launch or exe})
    return out


def _widget_layout(v):
    if not isinstance(v, dict):
        raise ValueError
    out = {}
    for wid, entry in v.items():
        if wid not in WIDGET_IDS or not isinstance(entry, dict):
            continue
        clean = {}
        for key in ("x", "y"):
            val = entry.get(key)
            if isinstance(val, int) and not isinstance(val, bool) and -20000 <= val <= 20000:
                clean[key] = val
        if isinstance(entry.get("visible"), bool):
            clean["visible"] = entry["visible"]
        out[wid] = clean
    return out


def _cells(v):
    if not isinstance(v, dict) or len(v) > 2000:
        raise ValueError
    out = {}
    for name, cell in v.items():
        if (isinstance(name, str) and 0 < len(name) <= 260 and isinstance(cell, list) and len(cell) == 2
                and all(isinstance(c, int) and not isinstance(c, bool) and 0 <= c <= 500 for c in cell)):
            out[name] = list(cell)
    return out


def _place(v):
    if v is None:
        return None
    if isinstance(v, dict):
        name, lat, lon = v.get("name"), v.get("lat"), v.get("lon")
        if (isinstance(name, str) and 0 < len(name) <= 80 and isinstance(lat, (int, float))
                and isinstance(lon, (int, float)) and not isinstance(lat, bool) and not isinstance(lon, bool)
                and math.isfinite(lat) and math.isfinite(lon) and -90 <= lat <= 90 and -180 <= lon <= 180):
            return {"name": name, "lat": float(lat), "lon": float(lon)}
    raise ValueError


def _widget_flags(v):
    if not isinstance(v, dict):
        raise ValueError
    return {wid: bool(v[wid]) for wid in WIDGET_IDS if isinstance(v.get(wid), bool)}


_PREF_SCHEMA: dict[str, Callable] = {
    "theme_variant": _choice("dark", "light", "auto"),
    "accent": _hex_color_or_none,
    "widgets": _widget_flags,
    "icon_style": _choice("native", "plate"),
    "dock_icon_size": _int(32, 72),
    "wallpaper": _str(300),
    "wallpaper_fit": _choice("fill", "fit", "center"),
    "widget_alpha": _int(30, 100),
    "wallpaper_on_switch": _bool,
}


def _mode_prefs(v):
    if not isinstance(v, dict):
        raise ValueError
    out = {}
    for mode, prefs in v.items():
        if mode not in MODES or not isinstance(prefs, dict):
            continue
        clean = {}
        for key, val in prefs.items():
            check = _PREF_SCHEMA.get(key)
            if check is None:
                continue
            try:
                clean[key] = check(val)
            except ValueError:
                pass
        out[mode] = clean
    return out


SCHEMA: dict[str, Callable] = {
    "theme": _theme_id,
    "profile": _choice(*MODES),
    "mode_prefs": _mode_prefs,
    "dock_pins": _pins,
    "dock_position": _choice("bottom", "left"),
    "dock_style": _choice("pill", "panel"),
    "dock_mode": _choice("smart", "autohide", "always"),
    "dock_icon_size": _int(32, 72),
    "dock_magnify": _bool,
    "dock_edge_gap": _int(0, 24),
    "icon_style": _choice("native", "plate"),
    "menubar_layout": _choice("macos", "gnome"),
    "menubar_mode": _choice("always", "autohide"),
    "clock_24h": _bool,
    "hide_taskbar": _bool,
    "style_windows": _bool,
    "desktop_icons": _bool,
    "win_key_launchpad": _bool,
    "widget_layout": _widget_layout,
    "widget_alpha": _int(30, 100),
    "desktop_icon_cells": _cells,
    "notes_text": _str(200_000),
    "week_start": _one_of_ints(0, 6),
    "units": _choice("metric", "imperial"),
    "weather_place": _place,
    "weather_auto_location": _bool,
    "original_wallpaper": _str(1024),
    "wallpaper_on_switch": _bool,
}


def sanitize(raw: Any) -> dict:
    """Keep only known keys whose values pass validation."""
    if not isinstance(raw, dict):
        return {}
    clean: dict = {}
    for key, check in SCHEMA.items():
        if key in raw:
            try:
                clean[key] = check(raw[key])
            except (ValueError, TypeError):
                pass
    return clean


class Settings(QObject):
    changed = pyqtSignal(str)   # emits the key that changed

    def __init__(self) -> None:
        super().__init__()
        self.path = settings_dir() / "settings.json"
        self._data: dict = {}
        self.load()

    def load(self) -> None:
        try:
            if self.path.exists() and self.path.stat().st_size > MAX_FILE_BYTES:
                raise ValueError("settings file too large")
            raw = json.loads(self.path.read_text(encoding="utf-8")) if self.path.exists() else {}
            self._data = sanitize(raw)
        except (OSError, ValueError, UnicodeDecodeError, RecursionError):
            try:                                          # keep the broken file for inspection, start clean
                self.path.replace(self.path.with_suffix(".corrupt.json"))
            except OSError:
                pass
            self._data = {}

    def get(self, key: str, default=None):
        return self._data.get(key, default)

    def set(self, key: str, value) -> bool:
        """Validate and store a value. Returns False (and stores nothing) if the value is not acceptable."""
        check = SCHEMA.get(key)
        if check is None:
            return False
        try:
            value = check(value)
        except (ValueError, TypeError):
            return False
        if self._data.get(key) == value and key in self._data:
            return True
        self._data[key] = value
        self._write()
        self.changed.emit(key)
        return True

    def reset(self) -> None:
        self._data = {}
        self._write()
        self.changed.emit("*")

    def _write(self) -> None:
        tmp = self.path.with_suffix(".tmp")
        try:
            tmp.write_text(json.dumps(self._data, indent=2, allow_nan=False), encoding="utf-8")
            os.replace(tmp, self.path)                    # atomic on Windows and POSIX
        except (OSError, ValueError):
            try:
                tmp.unlink()
            except OSError:
                pass
