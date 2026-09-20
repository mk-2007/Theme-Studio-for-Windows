"""Desktop profiles: one click switches the whole look-and-feel."""
from __future__ import annotations

from .settings import Settings
from .theme import ThemeManager

PROFILES: dict[str, dict] = {
    "macos": {
        "label": "macOS",
        "theme_prefix": "macos",
        "dock_position": "bottom", "dock_style": "pill", "dock_mode": "smart",
        "dock_icon_size": 44, "dock_magnify": True,
        "icon_style": "plate", "menubar_layout": "macos",
    },
    "ubuntu": {
        "label": "Ubuntu (GNOME)",
        "theme_prefix": "ubuntu",
        "dock_position": "left", "dock_style": "panel", "dock_mode": "smart",
        "dock_icon_size": 44, "dock_magnify": False,
        "icon_style": "native", "menubar_layout": "gnome",
    },
}


def apply_profile(settings: Settings, tm: ThemeManager, name: str) -> None:
    profile = PROFILES.get(name)
    if profile is None:
        return
    for key, value in profile.items():
        if key not in ("label", "theme_prefix"):
            settings.set(key, value)
    tm.set_theme(f"{profile['theme_prefix']}_{tm.theme.mode}")
    settings.set("profile", name)
