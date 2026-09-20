"""Dock data model: pinned apps + running apps, kept in sync with Windows."""
from __future__ import annotations

import os
import subprocess
from dataclasses import dataclass, field

import psutil
from PyQt6.QtCore import QFileInfo, QObject, QTimer, pyqtSignal

from . import winapi
from .settings import Settings
from .system import pretty_name


@dataclass
class DockItem:
    key: str                      # lower-cased process image name, e.g. "chrome.exe"
    name: str
    exe: str = ""
    launch: str = ""
    pinned: bool = False
    hwnds: list[int] = field(default_factory=list)   # front-to-back
    active: bool = False

    @property
    def running(self) -> bool:
        return bool(self.hwnds)

    @property
    def can_pin(self) -> bool:
        return bool(self.exe or self.launch) and not self.key.startswith("uwp:")

    @property
    def icon_path(self) -> str:
        return self.launch if self.launch.lower().endswith(".lnk") else self.exe


def key_for_path(path: str) -> str:
    return os.path.basename(path).lower()


def default_pins() -> list[dict]:
    env = os.environ
    windir = env.get("SystemRoot", r"C:\Windows")
    pf = env.get("ProgramFiles", r"C:\Program Files")
    pf86 = env.get("ProgramFiles(x86)", r"C:\Program Files (x86)")
    local = env.get("LOCALAPPDATA", "")
    candidates = [
        ("File Explorer", os.path.join(windir, "explorer.exe")),
        ("Microsoft Edge", os.path.join(pf86, "Microsoft", "Edge", "Application", "msedge.exe")),
        ("Google Chrome", os.path.join(pf, "Google", "Chrome", "Application", "chrome.exe")),
        ("Google Chrome", os.path.join(pf86, "Google", "Chrome", "Application", "chrome.exe")),
        ("Visual Studio Code", os.path.join(local, "Programs", "Microsoft VS Code", "Code.exe")),
        ("Notepad", os.path.join(windir, "System32", "notepad.exe")),
        ("Command Prompt", os.path.join(windir, "System32", "cmd.exe")),
    ]
    pins, seen = [], set()
    for name, path in candidates:
        if name in seen or not os.path.exists(path):
            continue
        seen.add(name)
        pins.append({"name": name, "exe": path, "launch": path})
    return pins


def launch_item(item: DockItem) -> bool:
    target = item.launch or item.exe
    if not target:
        return False
    try:
        if winapi.IS_WINDOWS:
            os.startfile(target)  # type: ignore[attr-defined]
        else:
            subprocess.Popen([target])
        return True
    except OSError as exc:
        print(f"[dock] could not launch {target}: {exc}")
        return False


class AppTracker(QObject):
    """Polls Windows for open app windows and merges them with the pinned list."""

    changed = pyqtSignal()

    def __init__(self, settings: Settings, parent=None):
        super().__init__(parent)
        self._settings = settings
        self._pins: list[dict] = self._load_pins()
        self._running: dict[str, DockItem] = {}
        self._order: list[str] = []          # stable order for unpinned running apps
        self._proc_cache: dict[int, tuple[str, str]] = {}
        self._signature: tuple | None = None
        self._all_hwnds: list[int] = []
        self._timer = QTimer(self, interval=600)
        self._timer.timeout.connect(self.refresh)

    # ------------------------------------------------------------- lifecycle
    def start(self) -> None:
        self.refresh(force=True)
        self._timer.start()

    def stop(self) -> None:
        self._timer.stop()

    # ------------------------------------------------------------- pins
    def _load_pins(self) -> list[dict]:
        raw = self._settings.get("dock_pins")
        if not isinstance(raw, list):
            raw = default_pins()
            self._settings.set("dock_pins", raw)
        pins = []
        for entry in raw:
            if isinstance(entry, dict) and entry.get("name") and (entry.get("exe") or entry.get("launch")):
                pins.append({"name": entry["name"], "exe": entry.get("exe", ""),
                             "launch": entry.get("launch") or entry.get("exe", "")})
        return pins

    def _save_pins(self) -> None:
        self._settings.set("dock_pins", self._pins)

    def is_pinned(self, key: str) -> bool:
        return any(key_for_path(p["exe"] or p["launch"]) == key for p in self._pins)

    def pin(self, item: DockItem) -> None:
        if not item.can_pin or self.is_pinned(item.key):
            return
        self._pins.append({"name": item.name, "exe": item.exe, "launch": item.launch or item.exe})
        self._save_pins()
        self.refresh(force=True)

    def pin_path(self, path: str) -> bool:
        """Pin a file dropped onto the dock (.exe or .lnk)."""
        path = os.path.normpath(path)
        if not os.path.exists(path):
            return False
        exe = path
        if path.lower().endswith(".lnk"):
            exe = QFileInfo(path).symLinkTarget() or path
        base = os.path.splitext(os.path.basename(path))[0]
        name = pretty_name(os.path.basename(exe)) if not path.lower().endswith(".lnk") else base
        key = key_for_path(exe)
        if self.is_pinned(key):
            return False
        self._pins.append({"name": name, "exe": os.path.normpath(exe), "launch": path})
        self._save_pins()
        self.refresh(force=True)
        return True

    def unpin(self, key: str) -> None:
        before = len(self._pins)
        self._pins = [p for p in self._pins if key_for_path(p["exe"] or p["launch"]) != key]
        if len(self._pins) != before:
            self._save_pins()
            self.refresh(force=True)

    # ------------------------------------------------------------- polling
    def _proc_info(self, pid: int) -> tuple[str, str] | None:
        hit = self._proc_cache.get(pid)
        if hit:
            return hit
        try:
            proc = psutil.Process(pid)
            name = proc.name()
        except (psutil.Error, OSError):
            return None
        try:
            exe = proc.exe()
        except (psutil.Error, OSError):
            exe = ""
        if len(self._proc_cache) > 300:
            self._proc_cache.clear()
        self._proc_cache[pid] = (name, exe)
        return name, exe

    def refresh(self, force: bool = False) -> None:
        own_pid = os.getpid()
        foreground = winapi.get_foreground_window()
        running: dict[str, DockItem] = {}
        self._all_hwnds = []
        for hwnd in winapi.list_app_windows():
            pid = winapi.get_window_pid(hwnd)
            if pid == own_pid:
                continue
            info = self._proc_info(pid)
            if info is None:
                continue
            self._all_hwnds.append(hwnd)
            name, exe = info
            if name.lower() == "applicationframehost.exe":       # UWP: one entry per window
                key, display, exe = f"uwp:{hwnd}", winapi.get_window_title(hwnd) or "App", ""
            else:
                key, display = name.lower(), pretty_name(name)
            item = running.get(key)
            if item is None:
                item = running[key] = DockItem(key=key, name=display, exe=exe, launch=exe)
            item.hwnds.append(hwnd)
            if hwnd == foreground:
                item.active = True

        self._running = running
        self._order = [k for k in self._order if k in running] + \
                      [k for k in running if k not in self._order]

        signature = tuple((k, tuple(v.hwnds), v.active) for k, v in running.items()) + (len(self._pins),)
        if force or signature != self._signature:
            self._signature = signature
            self.changed.emit()

    def window_handles(self) -> list[int]:
        """Every app window seen in the last poll (front-to-back)."""
        return list(self._all_hwnds)

    # ------------------------------------------------------------- model
    def items(self) -> list[DockItem]:
        out: list[DockItem] = []
        pinned_keys: set[str] = set()
        for pin in self._pins:
            key = key_for_path(pin["exe"] or pin["launch"])
            pinned_keys.add(key)
            run = self._running.get(key)
            out.append(DockItem(key=key, name=pin["name"], exe=pin["exe"], launch=pin["launch"],
                                pinned=True,
                                hwnds=list(run.hwnds) if run else [],
                                active=run.active if run else False))
        for key in self._order:
            if key in pinned_keys:
                continue
            run = self._running[key]
            out.append(DockItem(key=run.key, name=run.name, exe=run.exe, launch=run.launch,
                                pinned=False, hwnds=list(run.hwnds), active=run.active))
        return out
