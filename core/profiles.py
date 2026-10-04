"""Desktop modes: macOS and Ubuntu (Linux). Each mode has its own theme, widgets, icon style and wallpaper,
remembered separately, so switching modes restores exactly how you left each one."""
from __future__ import annotations

from . import winapi
from .settings import WIDGET_IDS, Settings
from .theme import ThemeManager

PROFILES: dict[str, dict] = {
    "macos": {
        "label": "macOS",
        "theme_prefix": "macos",
        "dock_position": "bottom", "dock_style": "pill", "dock_mode": "smart",
        "dock_edge_gap": 4, "icon_style": "plate", "menubar_layout": "macos",
    },
    "ubuntu": {
        "label": "Ubuntu (Linux)",
        "theme_prefix": "ubuntu",
        "dock_position": "left", "dock_style": "panel", "dock_mode": "smart",
        "dock_edge_gap": 0, "icon_style": "native", "menubar_layout": "gnome",
    },
}

DEFAULT_MODE_PREFS = {
    "theme_variant": "dark",
    "widgets": {wid: (wid != "notes") for wid in WIDGET_IDS},
    "icon_style": None,        # None = use the mode's own default above
    "dock_icon_size": 44,
    "widget_alpha": 82,
    "wallpaper": "",
    "wallpaper_fit": "fill",
    "wallpaper_on_switch": False,
}


def mode_prefs(settings: Settings, mode: str) -> dict:
    stored = settings.get("mode_prefs", {}).get(mode, {})
    merged = dict(DEFAULT_MODE_PREFS)
    merged["widgets"] = dict(DEFAULT_MODE_PREFS["widgets"])
    merged.update({k: v for k, v in stored.items() if k != "widgets"})
    merged["widgets"].update(stored.get("widgets", {}))
    return merged


def set_mode_pref(settings: Settings, mode: str, key: str, value) -> None:
    all_prefs = dict(settings.get("mode_prefs", {}))
    this_mode = dict(all_prefs.get(mode, {}))
    this_mode[key] = value
    all_prefs[mode] = this_mode
    settings.set("mode_prefs", all_prefs)


def set_mode_widget(settings: Settings, mode: str, widget_id: str, visible: bool) -> None:
    all_prefs = dict(settings.get("mode_prefs", {}))
    this_mode = dict(all_prefs.get(mode, {}))
    widgets = dict(this_mode.get("widgets", DEFAULT_MODE_PREFS["widgets"]))
    widgets[widget_id] = visible
    this_mode["widgets"] = widgets
    all_prefs[mode] = this_mode
    settings.set("mode_prefs", all_prefs)


def _resolve_variant(variant: str) -> str:
    if variant == "auto":
        return "dark" if winapi.get_windows_dark_mode() else "light"
    return variant if variant in ("dark", "light") else "dark"


def apply_profile(settings: Settings, tm: ThemeManager, name: str) -> None:
    """Switch to `name` (macos/ubuntu), applying that mode's saved theme, dock, icons and widgets."""
    base = PROFILES.get(name)
    if base is None:
        return
    prefs = mode_prefs(settings, name)
    settings.set("profile", name)     # set first: any live listener that persists changes back into
                                       # mode_prefs (widget visibility, icon style...) must target this mode
    for key, value in base.items():
        if key not in ("label", "theme_prefix"):
            settings.set(key, value)
    settings.set("icon_style", prefs["icon_style"] or base["icon_style"])
    settings.set("dock_icon_size", prefs["dock_icon_size"])
    settings.set("widget_alpha", prefs["widget_alpha"])
    tm.set_theme(f"{base['theme_prefix']}_{_resolve_variant(prefs['theme_variant'])}")

    layout = dict(settings.get("widget_layout", {}))
    for wid, visible in prefs["widgets"].items():
        entry = dict(layout.get(wid, {}))
        entry["visible"] = bool(visible)
        layout[wid] = entry
    settings.set("widget_layout", layout)

    if prefs.get("wallpaper_on_switch") and prefs.get("wallpaper"):
        if not settings.get("original_wallpaper"):
            settings.set("original_wallpaper", winapi.get_wallpaper_path())
        winapi.set_wallpaper_fit(prefs.get("wallpaper_fit", "fill"))
        winapi.set_wallpaper_path(prefs["wallpaper"])
