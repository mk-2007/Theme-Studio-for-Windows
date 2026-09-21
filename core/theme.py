"""Theme engine: JSON themes -> colors/metrics/fonts, switchable live."""
from __future__ import annotations

import json
from pathlib import Path

from PyQt6.QtCore import QObject, pyqtSignal
from PyQt6.QtGui import QColor, QFont

from .paths import resource_root

THEMES_DIR = resource_root() / "themes"


class Theme:
    def __init__(self, data: dict):
        self.id: str = data["id"]
        self.name: str = data["name"]
        self.mode: str = data.get("mode", "dark")
        self.pair: str | None = data.get("pair")
        self.font_families: list[str] = data.get("font_family", ["Segoe UI"])
        self.font_size: int = data.get("font_size", 13)
        self._metrics: dict = data.get("metrics", {})
        self._colors: dict[str, QColor] = {
            key: QColor(*value) for key, value in data.get("colors", {}).items()
        }

    def color(self, key: str) -> QColor:
        return QColor(self._colors[key])

    def rgba(self, key: str) -> str:
        """CSS-style rgba() string for use in Qt style sheets."""
        c = self._colors[key]
        return f"rgba({c.red()}, {c.green()}, {c.blue()}, {c.alpha()})"

    def metric(self, key: str, default: int = 0) -> int:
        return int(self._metrics.get(key, default))


class ThemeManager(QObject):
    """Loads every *.json in /themes and broadcasts changes."""

    changed = pyqtSignal()

    def __init__(self, themes_dir: Path = THEMES_DIR):
        super().__init__()
        self._themes: dict[str, Theme] = {}
        for path in sorted(themes_dir.glob("*.json")):
            try:
                theme = Theme(json.loads(path.read_text(encoding="utf-8")))
                self._themes[theme.id] = theme
            except Exception as exc:  # a broken theme file must never stop the shell
                print(f"[theme] skipped {path.name}: {exc}")
        if not self._themes:
            raise RuntimeError(f"No themes found in {themes_dir}")
        self._current = next(iter(self._themes.values()))

    @property
    def theme(self) -> Theme:
        return self._current

    def ids(self) -> list[str]:
        return list(self._themes)

    def names(self) -> list[tuple[str, str]]:
        return [(t.id, t.name) for t in self._themes.values()]

    def set_theme(self, theme_id: str) -> None:
        theme = self._themes.get(theme_id)
        if theme is None or theme is self._current:
            return
        self._current = theme
        self.changed.emit()

    def toggle_mode(self) -> None:
        if self._current.pair:
            self.set_theme(self._current.pair)

    def font(self, size: int | None = None, bold: bool = False) -> QFont:
        font = QFont()
        font.setFamilies(self._current.font_families)
        font.setPixelSize(int(size or self._current.font_size))
        font.setWeight(QFont.Weight.DemiBold if bold else QFont.Weight.Normal)
        return font
