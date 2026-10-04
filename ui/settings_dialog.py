"""Settings window: appearance, startup, dock, widgets, weather."""
from __future__ import annotations

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import (QCheckBox, QComboBox, QDialog, QFileDialog, QFormLayout, QHBoxLayout,
                             QLabel, QLineEdit, QPushButton, QScrollArea, QSlider, QTabWidget,
                             QVBoxLayout, QWidget)

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

        # ---- desktop style (macOS / Ubuntu, each with its own theme, widgets, icons, wallpaper)
        root.addWidget(self._header("Desktop style"))
        hint = QLabel("Switch between a macOS-style desktop and an Ubuntu (Linux)-style desktop. "
                      "Each keeps its own theme, widgets, icons and wallpaper.")
        hint.setWordWrap(True)
        hint.setObjectName("hint")
        root.addWidget(hint)
        self.tabs = QTabWidget()
        self._mode_widgets: dict[str, dict] = {}
        for mode_key, mode_label in (("macos", "macOS"), ("ubuntu", "Ubuntu (Linux)")):
            self.tabs.addTab(self._build_mode_tab(mode_key), mode_label)
        self.tabs.setCurrentIndex(0 if settings.get("profile", "macos") == "macos" else 1)
        root.addWidget(self.tabs)

        # ---- appearance (applies everywhere)
        root.addWidget(self._header("Appearance"))
        form = QFormLayout()
        self.clock24 = self._check("24-hour clock", "clock_24h", False)
        form.addRow("", self.clock24)
        root.addLayout(form)
        root.addWidget(self._check("Recolor app title bars to match the theme (Windows 11)", "style_windows", True))
        root.addWidget(self._check("Show Theme Studio desktop icons (hides the Windows ones)", "desktop_icons", True))
        self.menubar_hide = QCheckBox("Auto-hide the top bar")
        self.menubar_hide.setChecked(settings.get("menubar_mode", "always") == "autohide")
        self.menubar_hide.toggled.connect(lambda c: settings.set("menubar_mode", "autohide" if c else "always"))
        root.addWidget(self.menubar_hide)
        self.winkey = self._check("Windows key opens Launchpad instead of the Start menu", "win_key_launchpad", True)
        root.addWidget(self.winkey)

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
        gap_row = QHBoxLayout()
        gap_row.addWidget(QLabel("Distance from screen edge"))
        self.gap_slider = QSlider(Qt.Orientation.Horizontal)
        self.gap_slider.setRange(0, 20)
        self.gap_slider.setValue(int(settings.get("dock_edge_gap", 4)))
        self.gap_label = QLabel(f"{self.gap_slider.value()} px")
        self.gap_slider.valueChanged.connect(self._gap_changed)
        gap_row.addWidget(self.gap_slider, 1)
        gap_row.addWidget(self.gap_label)
        root.addLayout(gap_row)

        # ---- widget content (which widgets are shown per mode is set in the Desktop style tabs above)
        root.addWidget(self._header("Widget content"))
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
    def _build_mode_tab(self, mode: str) -> QWidget:
        """One tab: this mode's theme variant, widgets, icon style, wallpaper - all remembered per mode."""
        prefs = profiles.mode_prefs(self._s, mode)
        page = QWidget()
        page.setObjectName("modePage")
        page.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        lay = QVBoxLayout(page)
        lay.setContentsMargins(14, 14, 14, 14)
        lay.setSpacing(10)
        state: dict = {}
        self._mode_widgets[mode] = state

        use_btn = QPushButton(f"Switch to {profiles.PROFILES[mode]['label']} now")
        use_btn.clicked.connect(lambda: profiles.apply_profile(self._s, self._tm, mode))
        lay.addWidget(use_btn)

        form = QFormLayout()
        variant = QComboBox()
        variant.addItem("Dark", "dark")
        variant.addItem("Light", "light")
        variant.addItem("Match Windows", "auto")
        variant.setCurrentIndex(max(0, variant.findData(prefs["theme_variant"])))
        variant.currentIndexChanged.connect(
            lambda: self._set_mode_pref(mode, "theme_variant", variant.currentData()))
        form.addRow("Appearance", variant)
        state["variant"] = variant

        icon_style = QComboBox()
        icon_style.addItem("Native Windows icons", "native")
        icon_style.addItem("Rounded icons", "plate")
        default_icon = profiles.PROFILES[mode]["icon_style"]
        icon_style.setCurrentIndex(max(0, icon_style.findData(prefs["icon_style"] or default_icon)))
        icon_style.currentIndexChanged.connect(
            lambda: self._set_mode_pref(mode, "icon_style", icon_style.currentData()))
        form.addRow("App icons", icon_style)
        state["icon_style"] = icon_style
        lay.addLayout(form)

        lay.addWidget(QLabel("Widgets shown in this mode"))
        grid = QHBoxLayout()
        state["widgets"] = {}
        for wid, title in TITLES.items():
            box = QCheckBox(title)
            box.setChecked(bool(prefs["widgets"].get(wid, wid != "notes")))
            box.toggled.connect(lambda c, w=wid: self._set_mode_widget(mode, w, c))
            grid.addWidget(box)
            state["widgets"][wid] = box
        lay.addLayout(grid)

        alpha_row = QHBoxLayout()
        alpha_row.addWidget(QLabel("Widget transparency"))
        alpha = QSlider(Qt.Orientation.Horizontal)
        alpha.setRange(30, 100)
        alpha.setValue(int(prefs["widget_alpha"]))
        alpha_label = QLabel(f"{alpha.value()}%")
        alpha.valueChanged.connect(lambda v: (alpha_label.setText(f"{v}%"), self._set_mode_pref(mode, "widget_alpha", v)))
        alpha_row.addWidget(alpha, 1)
        alpha_row.addWidget(alpha_label)
        lay.addLayout(alpha_row)

        lay.addWidget(QLabel("Wallpaper for this mode"))
        wall_row = QHBoxLayout()
        wall_label = QLabel(prefs["wallpaper"] or "Not set - keeps your current wallpaper")
        wall_label.setWordWrap(True)
        browse = QPushButton("Choose image\u2026")
        browse.clicked.connect(lambda: self._choose_wallpaper(mode, wall_label))
        wall_row.addWidget(wall_label, 1)
        wall_row.addWidget(browse)
        lay.addLayout(wall_row)

        fit = QComboBox()
        fit.addItem("Fill screen", "fill")
        fit.addItem("Fit to screen", "fit")
        fit.addItem("Centered", "center")
        fit.setCurrentIndex(max(0, fit.findData(prefs["wallpaper_fit"])))
        fit.currentIndexChanged.connect(lambda: self._set_mode_pref(mode, "wallpaper_fit", fit.currentData()))
        on_switch = QCheckBox("Change the Windows wallpaper when I switch to this mode")
        on_switch.setChecked(bool(prefs["wallpaper_on_switch"]))
        on_switch.toggled.connect(lambda c: self._set_mode_pref(mode, "wallpaper_on_switch", c))
        lay.addWidget(fit)
        lay.addWidget(on_switch)
        lay.addStretch(1)
        state["wall_label"] = wall_label
        return page

    def _set_mode_pref(self, mode: str, key: str, value) -> None:
        profiles.set_mode_pref(self._s, mode, key, value)
        if self._s.get("profile", "macos") == mode:      # live-apply if this mode is the one showing now
            if key == "theme_variant":
                profiles.apply_profile(self._s, self._tm, mode)
            elif key == "icon_style":
                self._s.set("icon_style", value)
            elif key == "widget_alpha":
                self._s.set("widget_alpha", value)

    def _set_mode_widget(self, mode: str, widget_id: str, visible: bool) -> None:
        profiles.set_mode_widget(self._s, mode, widget_id, visible)
        if self._s.get("profile", "macos") == mode and self._widgets is not None:
            self._widgets.set_visible(widget_id, visible)

    def _choose_wallpaper(self, mode: str, label: QLabel) -> None:
        path, _filter = QFileDialog.getOpenFileName(
            self, "Choose a wallpaper", "", "Images (*.jpg *.jpeg *.png *.bmp)")
        if not path:
            return
        self._set_mode_pref(mode, "wallpaper", path)
        label.setText(path)

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
        profiles.set_mode_pref(self._s, self._s.get("profile", "macos"), "dock_icon_size", value)

    def _gap_changed(self, value: int) -> None:
        self.gap_label.setText(f"{value} px")
        self._s.set("dock_edge_gap", value)

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
            QTabWidget::pane {{ border: 1px solid {t.rgba('menu_border')}; border-radius: 10px;
                background: {t.rgba('panel_tile')}; top: -1px; }}
            QWidget#modePage {{ background: transparent; }}
            QTabBar::tab {{ background: transparent; color: {t.rgba('text_secondary')};
                padding: 7px 16px; margin-right: 2px; border-top-left-radius: 8px; border-top-right-radius: 8px; }}
            QTabBar::tab:selected {{ background: {t.rgba('panel_tile')}; color: {t.rgba('text')};
                font-weight: 600; }}
            QTabBar::tab:hover {{ color: {t.rgba('text')}; }}
        """)
