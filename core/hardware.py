"""Volume and brightness control. Both degrade gracefully if the optional packages are missing."""
from __future__ import annotations

import threading

from . import winapi


class Volume:
    def __init__(self) -> None:
        self._ep = None
        if not winapi.IS_WINDOWS:
            return
        try:
            from ctypes import POINTER, cast
            from comtypes import CLSCTX_ALL
            from pycaw.pycaw import AudioUtilities, IAudioEndpointVolume
            dev = AudioUtilities.GetSpeakers()
            ep = getattr(dev, "EndpointVolume", None)   # newer pycaw
            if ep is None:                              # older pycaw
                iface = dev.Activate(IAudioEndpointVolume._iid_, CLSCTX_ALL, None)
                ep = cast(iface, POINTER(IAudioEndpointVolume))
            self._ep = ep
        except Exception as exc:
            print(f"[volume] unavailable ({exc}); install with: python -m pip install pycaw")

    @property
    def available(self) -> bool:
        return self._ep is not None

    def get(self) -> float:
        try:
            return float(self._ep.GetMasterVolumeLevelScalar()) if self._ep else 0.0
        except Exception:
            return 0.0

    def set(self, value: float) -> None:
        try:
            if self._ep:
                self._ep.SetMasterVolumeLevelScalar(max(0.0, min(1.0, value)), None)
        except Exception:
            pass

    def muted(self) -> bool:
        try:
            return bool(self._ep.GetMute()) if self._ep else False
        except Exception:
            return False

    def set_muted(self, muted: bool) -> None:
        try:
            if self._ep:
                self._ep.SetMute(1 if muted else 0, None)
        except Exception:
            pass


class Brightness:
    """Laptop / DDC-capable display brightness via screen_brightness_control."""

    def __init__(self) -> None:
        self._sbc = None
        self._probed = False
        self._lock = threading.Lock()

    def _probe(self) -> None:
        if self._probed:
            return
        self._probed = True
        if not winapi.IS_WINDOWS:
            return
        try:
            import screen_brightness_control as sbc
            self._sbc = sbc
        except Exception as exc:
            print(f"[brightness] unavailable ({exc}); install: python -m pip install screen-brightness-control")

    def get(self) -> int | None:
        self._probe()
        if self._sbc is None:
            return None
        try:
            values = self._sbc.get_brightness()
            return int(values[0]) if values else None
        except Exception:
            return None

    def set(self, percent: int) -> None:
        self._probe()
        if self._sbc is None:
            return

        def work() -> None:
            with self._lock:
                try:
                    self._sbc.set_brightness(int(percent))
                except Exception:
                    pass
        threading.Thread(target=work, daemon=True).start()
