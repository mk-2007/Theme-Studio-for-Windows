"""Searchable index of installed apps (Start Menu + Store apps) and personal files."""
from __future__ import annotations

import json
import os
import subprocess
import threading
from dataclasses import dataclass
from pathlib import Path

from PyQt6.QtCore import QObject, pyqtSignal

from . import winapi

CREATE_NO_WINDOW = 0x08000000
_SKIP_WORDS = ("uninstall", "readme", "release notes", "documentation", "website", "license",
               "help", "manual", "eula")
_SKIP_DIRS = {"node_modules", ".git", "__pycache__", "venv", ".venv", "appdata", "$recycle.bin",
              "site-packages", "dist", "build"}


@dataclass
class AppEntry:
    name: str
    launch: str          # .lnk path, or "shell:AppsFolder\\<AppID>" for Store apps
    icon_path: str = ""  # path Qt can pull an icon from ("" -> generated letter icon)


@dataclass
class FileEntry:
    name: str
    path: str


def launch_target(target: str) -> None:
    try:
        if winapi.IS_WINDOWS:
            os.startfile(target)  # type: ignore[attr-defined]
        else:
            subprocess.Popen([target])
    except OSError as exc:
        print(f"[index] could not launch {target}: {exc}")


def _score(query: str, name: str) -> int:
    q, n = query.lower(), name.lower()
    if n == q:
        return 0
    if n.startswith(q):
        return 1
    if any(w.startswith(q) for w in n.replace("-", " ").replace("_", " ").split()):
        return 2
    if q in n:
        return 3
    return 99


class AppIndex(QObject):
    apps_ready = pyqtSignal()

    def __init__(self) -> None:
        super().__init__()
        self.apps: list[AppEntry] = []
        self.files: list[FileEntry] = []
        self._started = False

    def build_async(self) -> None:
        if self._started:
            return
        self._started = True
        threading.Thread(target=self._build, daemon=True).start()

    # ------------------------------------------------------------ building
    def _build(self) -> None:
        apps = self._scan_start_menu()
        self.apps = sorted(apps, key=lambda a: a.name.lower())
        self.apps_ready.emit()
        store = self._scan_store_apps({a.name.lower() for a in apps})
        if store:
            self.apps = sorted(self.apps + store, key=lambda a: a.name.lower())
            self.apps_ready.emit()
        self.files = self._scan_files()

    @staticmethod
    def _scan_start_menu() -> list[AppEntry]:
        roots = [os.path.join(os.environ.get("ProgramData", r"C:\ProgramData"),
                              "Microsoft", "Windows", "Start Menu", "Programs"),
                 os.path.join(os.environ.get("APPDATA", ""), "Microsoft", "Windows",
                              "Start Menu", "Programs")]
        found: dict[str, AppEntry] = {}
        for root in roots:
            if not root or not os.path.isdir(root):
                continue
            for dirpath, _dirs, files in os.walk(root):
                for fn in files:
                    if not fn.lower().endswith(".lnk"):
                        continue
                    name = fn[:-4]
                    if any(w in name.lower() for w in _SKIP_WORDS):
                        continue
                    found.setdefault(name.lower(), AppEntry(name, os.path.join(dirpath, fn),
                                                            os.path.join(dirpath, fn)))
        return list(found.values())

    @staticmethod
    def _scan_store_apps(existing: set[str]) -> list[AppEntry]:
        if not winapi.IS_WINDOWS:
            return []
        try:
            out = subprocess.run(
                ["powershell", "-NoProfile", "-Command", "Get-StartApps | ConvertTo-Json -Compress"],
                capture_output=True, text=True, timeout=25, creationflags=CREATE_NO_WINDOW).stdout
            data = json.loads(out) if out.strip() else []
        except Exception:
            return []
        if isinstance(data, dict):
            data = [data]
        result = []
        for item in data:
            name, app_id = item.get("Name", ""), item.get("AppID", "")
            if name and "!" in app_id and name.lower() not in existing:
                result.append(AppEntry(name, f"shell:AppsFolder\\{app_id}", f"shell:AppsFolder\\{app_id}"))
        return result

    @staticmethod
    def _scan_files() -> list[FileEntry]:
        home = Path.home()
        entries: list[FileEntry] = []
        for folder in ("Desktop", "Documents", "Downloads", "Pictures", "Videos", "Music"):
            base = home / folder
            if not base.is_dir():
                continue
            base_depth = len(base.parts)
            for dirpath, dirs, files in os.walk(base):
                dirs[:] = [d for d in dirs if d.lower() not in _SKIP_DIRS and not d.startswith(".")]
                if len(Path(dirpath).parts) - base_depth >= 4:
                    dirs[:] = []
                for fn in files:
                    if not fn.startswith("."):
                        entries.append(FileEntry(fn, os.path.join(dirpath, fn)))
                if len(entries) > 40000:
                    return entries
        return entries

    # ------------------------------------------------------------ searching
    def search_apps(self, query: str, limit: int | None = None) -> list[AppEntry]:
        query = query.strip()
        if not query:
            return list(self.apps[:limit] if limit else self.apps)
        scored = [(s, a) for a in self.apps if (s := _score(query, a.name)) < 99]
        scored.sort(key=lambda t: (t[0], t[1].name.lower()))
        result = [a for _s, a in scored]
        return result[:limit] if limit else result

    def search_files(self, query: str, limit: int = 5) -> list[FileEntry]:
        query = query.strip().lower()
        if len(query) < 2:
            return []
        hits = [f for f in self.files if query in f.name.lower()]
        hits.sort(key=lambda f: (not f.name.lower().startswith(query), len(f.name)))
        return hits[:limit]
