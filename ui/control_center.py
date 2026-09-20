"""Control Center: quick toggles, brightness + volume sliders, media keys."""
from __future__ import annotations

import threading
from typing import Callable

from PyQt6.QtCore import QPoint, QPointF, QRectF, Qt, QTimer, pyqtSignal
from PyQt6.QtGui import QColor, QPainter, QPen
from PyQt6.QtWidgets import QGridLayout, QHBoxLayout, QLabel, QVBoxLayout, QWidget

from core import system, winapi
from core.hardware import Brightness, Volume
from core.theme import ThemeManager
from . import glyphs

PANEL_W = 328


class Tile(QWidget):
    clicked = pyqtSignal()

    def __init__(self, tm: ThemeManager, painter: Callable, title: str, subtitle: str = "") -> None:
        super().__init__()
        self._tm, self._paint_glyph = tm, painter
        self._title, self._subtitle = title, subtitle
        self._on = False
        self._hover = False
        self.setFixedSize(146, 56)

    def set_state(self, on: bool | None = None, subtitle: str | None = None) -> None:
        if on is not None:
            self._on = on
        if subtitle is not None:
            self._subtitle = subtitle
        self.update()

    def enterEvent(self, _e) -> None:
        self._hover = True
        self.update()

    def leaveEvent(self, _e) -> None:
        self._hover = False
        self.update()

    def mouseReleaseEvent(self, e) -> None:
        if e.button() == Qt.MouseButton.LeftButton and self.rect().contains(e.position().toPoint()):
            self.clicked.emit()

    def paintEvent(self, _e) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setRenderHint(QPainter.RenderHint.TextAntialiasing)
        t = self._tm.theme
        bg = QColor(t.color("panel_tile"))
        if self._hover:
            bg.setAlpha(min(255, bg.alpha() + 18))
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(bg)
        p.drawRoundedRect(QRectF(self.rect()), 14, 14)
        badge = QRectF(10, 12, 32, 32)
        p.setBrush(t.color("accent") if self._on else QColor(t.color("text").red(), t.color("text").green(),
                                                              t.color("text").blue(), 34))
        p.drawEllipse(badge)
        self._paint_glyph(p, badge.adjusted(7, 7, -7, -7), QColor(255, 255, 255) if self._on else t.color("text"))
        p.setFont(self._tm.font(13, True))
        p.setPen(t.color("text"))
        p.drawText(QRectF(50, 9, 92, 20), Qt.AlignmentFlag.AlignVCenter, self._title)
        p.setFont(self._tm.font(11))
        p.setPen(t.color("text_secondary"))
        sub = p.fontMetrics().elidedText(self._subtitle, Qt.TextElideMode.ElideRight, 90)
        p.drawText(QRectF(50, 28, 92, 18), Qt.AlignmentFlag.AlignVCenter, sub)


class PillSlider(QWidget):
    valueChanged = pyqtSignal(float)

    def __init__(self, tm: ThemeManager, painter: Callable) -> None:
        super().__init__()
        self._tm, self._paint_glyph = tm, painter
        self._value = 0.5
        self._enabled = True
        self.setFixedSize(PANEL_W - 28, 32)
        self.setCursor(Qt.CursorShape.PointingHandCursor)

    def value(self) -> float:
        return self._value

    def set_value(self, v: float, enabled: bool = True) -> None:
        self._value, self._enabled = max(0.0, min(1.0, v)), enabled
        self.update()

    def _set_from(self, x: float) -> None:
        if not self._enabled:
            return
        self._value = max(0.0, min(1.0, (x - 16) / max(1.0, self.width() - 32)))
        self.valueChanged.emit(self._value)
        self.update()

    def mousePressEvent(self, e) -> None:
        self._set_from(e.position().x())

    def mouseMoveEvent(self, e) -> None:
        if e.buttons() & Qt.MouseButton.LeftButton:
            self._set_from(e.position().x())

    def paintEvent(self, _e) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        t = self._tm.theme
        r = QRectF(self.rect())
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(t.color("panel_tile"))
        p.drawRoundedRect(r, 16, 16)
        fill_w = 32 + (r.width() - 32) * self._value
        p.setBrush(t.color("text") if self._enabled else t.color("text_secondary"))
        fill = QColor(t.color("text"))
        fill.setAlpha(210 if self._enabled else 70)
        p.setBrush(fill)
        p.save()
        p.setClipRect(QRectF(0, 0, fill_w, r.height()))
        p.drawRoundedRect(r, 16, 16)
        p.restore()
        knob = QColor(t.color("panel_bg"))
        knob.setAlpha(255)
        self._paint_glyph(p, QRectF(6, 4, 24, 24), knob if self._value > 0.08 else t.color("text_secondary"))


class MediaButton(QWidget):
    clicked = pyqtSignal()

    def __init__(self, tm: ThemeManager, painter: Callable) -> None:
        super().__init__()
        self._tm, self._paint_glyph = tm, painter
        self._hover = False
        self.setFixedSize(60, 40)

    def enterEvent(self, _e) -> None:
        self._hover = True
        self.update()

    def leaveEvent(self, _e) -> None:
        self._hover = False
        self.update()

    def mouseReleaseEvent(self, e) -> None:
        if e.button() == Qt.MouseButton.LeftButton and self.rect().contains(e.position().toPoint()):
            self.clicked.emit()

    def paintEvent(self, _e) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        t = self._tm.theme
        if self._hover:
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(t.color("hover"))
            p.drawRoundedRect(QRectF(self.rect()), 12, 12)
        self._paint_glyph(p, QRectF(15, 7, 30, 26), t.color("text"))


class ControlCenter(QWidget):
    dark_mode_requested = pyqtSignal()
    settings_requested = pyqtSignal()
    peek_requested = pyqtSignal()
    _wifi_found = pyqtSignal(object)

    def __init__(self, tm: ThemeManager, volume: Volume, brightness: Brightness) -> None:
        super().__init__(None, Qt.WindowType.Popup | Qt.WindowType.FramelessWindowHint
                         | Qt.WindowType.NoDropShadowWindowHint)
        self._tm, self._volume, self._brightness = tm, volume, brightness
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setFixedWidth(PANEL_W)

        self.wifi = Tile(tm, glyphs.draw_wifi, "Wi-Fi", "Checking\u2026")
        self.bluetooth = Tile(tm, glyphs.draw_bluetooth, "Bluetooth", "Open settings")
        self.dark = Tile(tm, glyphs.draw_contrast, "Dark Mode", "")
        self.focus = Tile(tm, glyphs.draw_moon, "Focus", "Do Not Disturb")
        self.night = Tile(tm, glyphs.draw_sun, "Night Light", "Open settings")
        self.widgets_tile = Tile(tm, glyphs.draw_widgets, "Widgets", "Peek at desktop")

        self.wifi.clicked.connect(lambda: self._open("ms-settings:network-wifi"))
        self.bluetooth.clicked.connect(lambda: self._open("ms-settings:bluetooth"))
        self.focus.clicked.connect(lambda: self._open("ms-settings:quietmomentshome"))
        self.night.clicked.connect(lambda: self._open("ms-settings:nightlight"))
        self.dark.clicked.connect(self._toggle_dark)
        self.widgets_tile.clicked.connect(lambda: (self.hide(), self.peek_requested.emit()))

        self.brightness_slider = PillSlider(tm, glyphs.draw_sun)
        self.volume_slider = PillSlider(tm, lambda p, r, c: glyphs.draw_speaker(p, r, c, self._volume.get(),
                                                                                  self._volume.muted()))
        self.brightness_slider.valueChanged.connect(lambda v: self._brightness.set(round(v * 100)))
        self.volume_slider.valueChanged.connect(self._on_volume)

        root = QVBoxLayout(self)
        root.setContentsMargins(14, 14, 14, 14)
        root.setSpacing(8)
        grid = QGridLayout()
        grid.setSpacing(8)
        for i, tile in enumerate((self.wifi, self.bluetooth, self.dark, self.focus, self.night, self.widgets_tile)):
            grid.addWidget(tile, i // 2, i % 2)
        root.addLayout(grid)

        self._labels: list[QLabel] = []
        root.addSpacing(4)
        root.addWidget(self._label("Display"))
        root.addWidget(self.brightness_slider)
        root.addWidget(self._label("Sound"))
        root.addWidget(self.volume_slider)

        media = QHBoxLayout()
        media.setSpacing(6)
        media.addStretch(1)
        for painter, vk in ((lambda p, r, c: glyphs.draw_skip(p, r, c, False), winapi.VK_MEDIA_PREV),
                            (glyphs.draw_play, winapi.VK_MEDIA_PLAY_PAUSE),
                            (lambda p, r, c: glyphs.draw_skip(p, r, c, True), winapi.VK_MEDIA_NEXT)):
            btn = MediaButton(tm, painter)
            btn.clicked.connect(lambda k=vk: winapi.send_media_key(k))
            media.addWidget(btn)
        media.addStretch(1)
        root.addLayout(media)

        footer = QHBoxLayout()
        footer.setSpacing(8)
        settings_btn = Tile(tm, glyphs.draw_controls, "Settings\u2026", "Theme Studio")
        lock_btn = Tile(tm, lambda p, r, c: glyphs.draw_moon(p, r, c), "Lock", "Lock screen")
        settings_btn.clicked.connect(lambda: (self.hide(), self.settings_requested.emit()))
        lock_btn.clicked.connect(lambda: (self.hide(), system.lock_screen()))
        footer.addWidget(settings_btn)
        footer.addWidget(lock_btn)
        root.addLayout(footer)

        self._wifi_found.connect(self._on_wifi)
        self._debounce = QTimer(self, singleShot=True, interval=90)
        tm.changed.connect(self.update)

    def _label(self, text: str) -> QLabel:
        lab = QLabel(text)
        lab.setStyleSheet(f"color: {self._tm.theme.rgba('text_secondary')}; font-weight: 600;"
                          f" font-size: 12px; padding-left: 4px;")
        self._labels.append(lab)
        return lab

    # ------------------------------------------------------------------ behaviour
    def _open(self, uri: str) -> None:
        self.hide()
        system.open_uri(uri)

    def _toggle_dark(self) -> None:
        self.dark_mode_requested.emit()
        QTimer.singleShot(80, self._refresh_dark)

    def _refresh_dark(self) -> None:
        dark = self._tm.theme.mode == "dark"
        self.dark.set_state(dark, "On" if dark else "Off")

    def _on_volume(self, v: float) -> None:
        if self._volume.muted() and v > 0:
            self._volume.set_muted(False)
        self._volume.set(v)
        self.volume_slider.update()

    def _on_wifi(self, ssid) -> None:
        self.wifi.set_state(bool(ssid), ssid or "Not connected")

    def show_at(self, anchor_global_right: int, top: int) -> None:
        for lab in self._labels:   # keep labels in sync with theme
            lab.setStyleSheet(f"color: {self._tm.theme.rgba('text_secondary')}; font-weight: 600;"
                              f" font-size: 12px; padding-left: 4px;")
        self._refresh_dark()
        b = self._brightness.get()
        self.brightness_slider.set_value((b or 0) / 100, enabled=b is not None)
        self.volume_slider.set_value(self._volume.get(), enabled=self._volume.available)
        self.wifi.set_state(False, "Checking\u2026")
        threading.Thread(target=lambda: self._wifi_found.emit(system.wifi_ssid()), daemon=True).start()
        self.adjustSize()
        self.move(QPoint(anchor_global_right - self.width(), top))
        self.show()

    def paintEvent(self, _e) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        t = self._tm.theme
        p.setBrush(t.color("panel_bg"))
        p.setPen(QPen(t.color("menu_border"), 1))
        p.drawRoundedRect(QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5), 20, 20)
