"""Settings window: appearance, startup, dock, widgets, weather."""
from __future__ import annotations

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import (QCheckBox, QComboBox, QDialog, QFormLayout, QHBoxLayout, QLabel,
                             QLineEdit, QPushButton, QScrollArea, QSlider, QVBoxLayout, QWidget)

import threading

from core import profiles, system, weather
from core.settings import Settings
from core.theme import ThemeManager
from .desktop_widgets import TITLES, WidgetManager


class SettingsDialog(QDialog):
    _geo_done = pyqtSignal(object, str)

    def __init__(self, tm: ThemeManager, settings: Settings, widgets: WidgetManager | None) -> None:
        super().__init__(None)
        self._tm, self._s, self._widgets = tm, settings, widgets
        self.setWindowTitle("Theme Studio Settings")
        self.resize(500, 720)
        self.setWindowFlag(Qt.WindowType.WindowStaysOnTopHint, True)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        content = QWidget()
        scroll.setWidget(content)
        outer.addWidget(scroll)
        root = QVBoxLayout(content)
        root.setContentsMargins(22, 14, 22, 20)
        root.setSpacing(6)

        # ---- desktop style
        root.addWidget(self._header("Desktop style"))
        style_row = QHBoxLayout()
        self.profile_box = QComboBox()
        for key, prof in profiles.PROFILES.items():
            self.profile_box.addItem(prof["label"], key)
        self.profile_box.setCurrentIndex(max(0, self.profile_box.findData(settings.get("profile", "macos"))))
        apply_btn = QPushButton("Apply style")
        apply_btn.clicked.connect(lambda: profiles.apply_profile(settings, tm, self.profile_box.currentData()))
        style_row.addWidget(self.profile_box, 1)
        style_row.addWidget(apply_btn)
        root.addLayout(style_row)
        hint = QLabel("Applies the matching theme, dock, top bar and icon style in one go. "
                      "You can still tweak each part below.")
        hint.setWordWrap(True)
        hint.setObjectName("hint")
        root.addWidget(hint)

        # ---- appearance
        root.addWidget(self._header("Appearance"))
        form = QFormLayout()
        self.theme_box = QComboBox()
        for theme_id, name in tm.names():
            self.theme_box.addItem(name, theme_id)
        self.theme_box.setCurrentIndex(max(0, self.theme_box.findData(tm.theme.id)))
        self.theme_box.currentIndexChanged.connect(lambda: tm.set_theme(self.theme_box.currentData()))
        form.addRow("Theme", self.theme_box)
        self.clock24 = self._check("24-hour clock", "clock_24h", False)
        form.addRow("", self.clock24)
        self.icon_style = QComboBox()
        self.icon_style.addItem("Native Windows icons", "native")
        self.icon_style.addItem("macOS rounded icons", "plate")
        self.icon_style.setCurrentIndex(0 if settings.get("icon_style", "plate") == "native" else 1)
        self.icon_style.currentIndexChanged.connect(lambda: settings.set("icon_style", self.icon_style.currentData()))
        form.addRow("App icons", self.icon_style)
        root.addLayout(form)
        root.addWidget(self._check("Recolor app title bars to match the theme (Windows 11)", "style_windows", True))
        root.addWidget(self._check("Show Theme Studio desktop icons (hides the Windows ones)", "desktop_icons", True))
        self.menubar_hide = QCheckBox("Auto-hide the top bar")
        self.menubar_hide.setChecked(settings.get("menubar_mode", "always") == "autohide")
        self.menubar_hide.toggled.connect(lambda c: settings.set("menubar_mode", "autohide" if c else "always"))
        root.addWidget(self.menubar_hide)

        # ---- startup
        root.addWidget(self._header("Startup"))
        self.autostart = QCheckBox("Start Theme Studio when I sign in")
        self.autostart.setChecked(system.autostart_enabled())
        self.autostart.toggled.connect(self._autostart_changed)
        self.hide_taskbar = self._check("Hide the Windows taskbar while running", "hide_taskbar", True)
        self.hide_taskbar.toggled.connect(lambda _c: self._autostart_changed(self.autostart.isChecked()))
        root.addWidget(self.autostart)
        root.addWidget(self.hide_taskbar)

        # ---- dock
        root.addWidget(self._header("Dock"))
        dock_form = QFormLayout()
        self.dock_pos = QComboBox()
        self.dock_pos.addItem("Bottom", "bottom")
        self.dock_pos.addItem("Left", "left")
        self.dock_pos.setCurrentIndex(0 if settings.get("dock_position", "bottom") == "bottom" else 1)
        self.dock_pos.currentIndexChanged.connect(lambda: settings.set("dock_position", self.dock_pos.currentData()))
        dock_form.addRow("Position", self.dock_pos)
        self.dock_style = QComboBox()
        self.dock_style.addItem("Floating pill (macOS)", "pill")
        self.dock_style.addItem("Side panel (Ubuntu)", "panel")
        self.dock_style.setCurrentIndex(0 if settings.get("dock_style", "pill") == "pill" else 1)
        self.dock_style.currentIndexChanged.connect(lambda: settings.set("dock_style", self.dock_style.currentData()))
        dock_form.addRow("Style", self.dock_style)
        self.dock_mode = QComboBox()
        self.dock_mode.addItem("Smart: hide when a window is in the way", "smart")
        self.dock_mode.addItem("Auto-hide: only show when I point at the edge", "autohide")
        self.dock_mode.addItem("Always visible (reserves screen space)", "always")
        self.dock_mode.setCurrentIndex(max(0, self.dock_mode.findData(settings.get("dock_mode", "smart"))))
        self.dock_mode.currentIndexChanged.connect(lambda: settings.set("dock_mode", self.dock_mode.currentData()))
        dock_form.addRow("Behavior", self.dock_mode)
        root.addLayout(dock_form)
        self.magnify = self._check("Magnify icons under the cursor (floating pill only)", "dock_magnify", True)
        root.addWidget(self.magnify)
        row = QHBoxLayout()
        row.addWidget(QLabel("Icon size"))
        self.size_slider = QSlider(Qt.Orientation.Horizontal)
        self.size_slider.setRange(36, 64)
        self.size_slider.setValue(int(settings.get("dock_icon_size", 44)))
        self.size_label = QLabel(f"{self.size_slider.value()} px")
        self.size_slider.valueChanged.connect(self._size_changed)
        row.addWidget(self.size_slider, 1)
        row.addWidget(self.size_label)
        root.addLayout(row)

        # ---- widgets
        root.addWidget(self._header("Widgets"))
        if widgets is not None:
            grid = QHBoxLayout()
            for wid, title in TITLES.items():
                box = QCheckBox(title)
                box.setChecked(widgets.is_visible(wid))
                box.toggled.connect(lambda c, w=wid: widgets.set_visible(w, c))
                grid.addWidget(box)
            root.addLayout(grid)
        wform = QFormLayout()
        self.week = QComboBox()
        self.week.addItem("Monday", 0)
        self.week.addItem("Sunday", 6)
        self.week.setCurrentIndex(0 if int(settings.get("week_start", 0)) == 0 else 1)
        self.week.currentIndexChanged.connect(lambda: settings.set("week_start", self.week.currentData()))
        wform.addRow("Week starts on", self.week)
        self.units = QComboBox()
        self.units.addItem("Celsius (\u00b0C)", "metric")
        self.units.addItem("Fahrenheit (\u00b0F)", "imperial")
        self.units.setCurrentIndex(0 if settings.get("units", "metric") == "metric" else 1)
        self.units.currentIndexChanged.connect(lambda: settings.set("units", self.units.currentData()))
        wform.addRow("Temperature", self.units)
        city_row = QHBoxLayout()
        self.city = QLineEdit()
        place = settings.get("weather_place")
        self.city.setPlaceholderText(place["name"] if place else "Auto-detect (by IP)")
        self.city_btn = QPushButton("Set city")
        self.city_btn.clicked.connect(self._find_city)
        city_row.addWidget(self.city, 1)
        city_row.addWidget(self.city_btn)
        wform.addRow("Weather city", city_row)
        root.addLayout(wform)
        self.status = QLabel("")
        root.addWidget(self.status)
        self._geo_done.connect(self._on_geo)

        # ---- footer
        foot = QHBoxLayout()
        reset = QPushButton("Reset widget positions")
        reset.clicked.connect(lambda: widgets.reset_positions() if widgets else None)
        close = QPushButton("Done")
        close.setDefault(True)
        close.clicked.connect(self.accept)
        foot.addWidget(reset)
        foot.addStretch(1)
        foot.addWidget(close)
        root.addSpacing(8)
        root.addLayout(foot)

        tm.changed.connect(self._style)
        self._style()

    # ---------------------------------------------------------------- helpers
    def _header(self, text: str) -> QLabel:
        lab = QLabel(text)
        lab.setObjectName("header")
        return lab

    def _check(self, text: str, key: str, default: bool) -> QCheckBox:
        box = QCheckBox(text)
        box.setChecked(bool(self._s.get(key, default)))
        box.toggled.connect(lambda c, k=key: self._s.set(k, c))
        return box

    def _autostart_changed(self, enabled: bool) -> None:
        system.set_autostart(enabled, bool(self._s.get("hide_taskbar", True)))

    def _size_changed(self, value: int) -> None:
        self.size_label.setText(f"{value} px")
        self._s.set("dock_icon_size", value)

    def _find_city(self) -> None:
        name = self.city.text().strip()
        if not name:
            self._s.set("weather_place", None)
            self.status.setText("Using automatic location.")
            return
        self.status.setText("Looking up\u2026")
        threading.Thread(target=self._geo_worker, args=(name,), daemon=True).start()

    def _geo_worker(self, name: str) -> None:
        try:
            self._geo_done.emit(weather.geocode(name), name)
        except Exception:
            self._geo_done.emit(None, "")

    def _on_geo(self, place, name: str) -> None:
        if place:
            self._s.set("weather_place", place)
            self.status.setText(f"Weather location set to {place['name']}.")
        else:
            self.status.setText("Could not find that city (or no connection).")

    def _style(self) -> None:
        t = self._tm.theme
        opaque = t.color("menu_bg")
        opaque.setAlpha(255)
        self.setFont(self._tm.font(13))
        self.setStyleSheet(f"""
            QDialog {{ background: {opaque.name()}; }}
            QLabel, QCheckBox {{ color: {t.rgba('text')}; }}
            QLabel#header {{ font-weight: 600; font-size: 15px; margin-top: 12px; }}
            QLabel#hint {{ color: {t.rgba('text_secondary')}; font-size: 12px; }}
            QScrollArea {{ background: transparent; }} QScrollArea > QWidget > QWidget {{ background: transparent; }}
            QComboBox, QLineEdit {{ background: {t.rgba('field_bg')}; color: {t.rgba('text')};
                border: 1px solid {t.rgba('menu_border')}; border-radius: 8px; padding: 5px 9px; }}
            QComboBox QAbstractItemView {{ background: {opaque.name()}; color: {t.rgba('text')};
                selection-background-color: {t.rgba('accent')}; }}
            QCheckBox::indicator {{ width: 16px; height: 16px; border-radius: 4px;
                border: 1px solid {t.rgba('text_secondary')}; background: {t.rgba('field_bg')}; }}
            QCheckBox::indicator:checked {{ background: {t.rgba('accent')}; border-color: {t.rgba('accent')}; }}
            QPushButton {{ background: {t.rgba('panel_tile')}; color: {t.rgba('text')};
                border: 1px solid {t.rgba('menu_border')}; border-radius: 8px; padding: 6px 14px; }}
            QPushButton:default {{ background: {t.rgba('accent')}; color: white; border: none; }}
            QPushButton:hover {{ border-color: {t.rgba('accent')}; }}
            QSlider::groove:horizontal {{ height: 5px; background: {t.rgba('panel_tile')}; border-radius: 2px; }}
            QSlider::sub-page:horizontal {{ background: {t.rgba('accent')}; border-radius: 2px; }}
            QSlider::handle:horizontal {{ width: 16px; height: 16px; margin: -6px 0; border-radius: 8px;
                background: white; border: 1px solid {t.rgba('menu_border')}; }}
        """)
