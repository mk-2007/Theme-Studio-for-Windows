"""JSON settings store in %APPDATA%/ThemeStudio/settings.json, with change signals."""
from __future__ import annotations

import json
import os
from pathlib import Path

from PyQt6.QtCore import QObject, pyqtSignal


def _settings_dir() -> Path:
    base = os.environ.get("APPDATA") or str(Path.home() / ".config")
    path = Path(base) / "ThemeStudio"
    path.mkdir(parents=True, exist_ok=True)
    return path


class Settings(QObject):
    changed = pyqtSignal(str)   # emits the key that changed

    def __init__(self) -> None:
        super().__init__()
        self.path = _settings_dir() / "settings.json"
        self._data: dict = {}
        self.load()

    def load(self) -> None:
        try:
            self._data = json.loads(self.path.read_text(encoding="utf-8"))
        except Exception:
            self._data = {}

    def get(self, key: str, default=None):
        return self._data.get(key, default)

    def set(self, key: str, value) -> None:
        if self._data.get(key) == value:
            return
        self._data[key] = value
        try:
            self.path.write_text(json.dumps(self._data, indent=2), encoding="utf-8")
        except OSError:
            pass
        self.changed.emit(key)
