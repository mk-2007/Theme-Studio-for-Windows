# Theme Studio

A complete macOS **or** Ubuntu (GNOME) desktop for Windows: top bar, dock, widgets, desktop icons, Launchpad /
Show Applications, Spotlight, Control Center and themed app title bars. It replaces the Windows taskbar.

## Install as a real app (no terminal needed afterwards)
1. Double-click **`install.bat`** (needs Python 3.10+ once, to build the app).
2. Wait a minute or two. It builds `ThemeStudio.exe`, installs it to `%LOCALAPPDATA%\Programs\ThemeStudio`,
   adds Start-menu and desktop shortcuts, makes it start with Windows, and launches it.

From then on it just runs in the background (tray icon near the clock). Launch it again from the Start menu or
desktop shortcut to open **Settings**. `uninstall.bat` removes it and puts the normal taskbar back.

Not ready to install? Double-click **`ThemeStudio.pyw`** or `run.bat` (no console window), or `run_debug.bat`
(shows errors). Logs are in `%APPDATA%\ThemeStudio\theme-studio.log` (tray icon -> Open log file).

## Safety net
- **Ctrl+Alt+Q** quits and restores everything.
- A tiny background guard process restores the Windows taskbar and desktop icons if Theme Studio ever crashes or is killed.
- `restore_taskbar.bat` does it by hand. Or: Ctrl+Shift+Esc -> Run new task -> `explorer.exe`.

## Style
Logo menu -> Desktop Style, tray icon, Settings -> Desktop style, or type "ubuntu style" / "macos style" in Spotlight.

| | macOS | Ubuntu (GNOME) |
|---|---|---|
| Top bar | menu bar | panel: Activities, centred clock, Wi-Fi / sound / battery / power |
| Dock | floating pill at the bottom, magnifying icons | left side panel, dots on the edge |
| Launchpad | paged glass grid, dots at the bottom | "Show Applications", dots on the right |
| Icons | rounded plates | native |

## The Windows taskbar is fully replaced
It is hidden and kept hidden (Explorer can re-show it; Theme Studio hides it again). The little chevron in the top bar
opens the real taskbar for a few seconds, so tray icons and notification flyouts stay reachable.

## Screen space
The dock hides when a window is in the way and slides back when you point at the edge (Settings -> Dock: Smart /
Auto-hide / Always visible). Its distance from the screen edge is adjustable (default 4 px).

## Hotkeys
Alt+Space Spotlight - Ctrl+Alt+L Launchpad - Ctrl+Alt+W peek at widgets (or click the clock) - Ctrl+Alt+Q quit

## Files
    install.bat / uninstall.bat      build + install / remove
    ThemeStudio.pyw, run*.bat        start without installing
    main.py                          entry point     core/  logic + Win32     ui/  every window     themes/*.json
