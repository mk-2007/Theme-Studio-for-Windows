# Theme Studio

A complete macOS **or** Ubuntu (GNOME) desktop experience for Windows: top bar, dock, widgets, desktop icons,
Launchpad / Show Applications, Spotlight, Control Center, themed app title bars.

## Run
    python -m pip install -r requirements.txt
    python -m pip install -r requirements-optional.txt   # optional: volume + brightness sliders
    python main.py                  # the Windows taskbar is hidden by default
    python main.py --keep-taskbar   # leave the Windows taskbar visible
    python main.py --restore-taskbar   # bring taskbar + desktop icons back if anything went wrong
Other flags: `--no-dock`, `--no-widgets`, `--theme ubuntu_dark`.

## Switch style
Logo menu -> Desktop Style, tray icon -> macOS style / Ubuntu style, Settings -> Desktop style, or type
"ubuntu style" / "macos style" in Spotlight. One click changes theme, top bar, dock, icons and fonts.

| | macOS | Ubuntu (GNOME) |
|---|---|---|
| Top bar | menu bar: logo menu, app menu, battery, search, Control Center, clock | panel: Activities, app name, centered clock, Wi-Fi / sound / battery / power |
| Dock | floating pill at the bottom, magnifying icons, Launchpad first | side panel on the left, running dots on the edge, Trash + Show Applications at the bottom |
| Icons | rounded "plate" icons | native icons |
| Accent | blue | Ubuntu orange |

## Screen space (no more wasted margin)
The dock **hides when a window is in the way** and slides back when you point at the screen edge (default "Smart").
Other modes in Settings -> Dock: Auto-hide (only shows when you point at the edge) and Always visible
(reserves space so maximized windows stop beside it). The top bar can also auto-hide. Only the top bar reserves
space by default, and it is just 26 px.

## Hotkeys
| Keys | Action |
|---|---|
| Alt+Space | Spotlight |
| Ctrl+Alt+L | Launchpad |
| Ctrl+Alt+W | Peek at widgets (also: click the clock) |
| Ctrl+Alt+Q | Quit and restore everything |

## Safety
If the taskbar or desktop icons are ever missing after a crash: run `restore_taskbar.bat`, or
Ctrl+Shift+Esc -> Run new task -> `explorer.exe`, or right-click the desktop -> View -> Show desktop icons.

## Features
- **Dock**: bottom or left, pill or panel, smart auto-hide, launch bounce, drag-to-pin, right-click menus, Recycle Bin.
- **Desktop icons**: your Desktop drawn macOS-style (top-right grid, rounded selection, drag to rearrange, double-click to open).
- **App title bars**: recolored to match the theme on Windows 11 (toggle in Settings).
- **Widgets**: Weather, Clock, System, Calendar, Notes on the desktop layer.
- **Launchpad / Show Applications**, **Spotlight**, **Control Center**, **Settings**.

## Build a standalone .exe
Double-click `build_exe.bat` -> `dist\ThemeStudio.exe`.

## Layout
    main.py                 entry point, wiring, tray, hotkeys
    core/winapi.py          every Win32 call (ctypes)     core/profiles.py   macOS / Ubuntu presets
    core/theme.py + themes/*.json   themes (drop in a .json to add one)
    core/apps.py, index.py, winstyle.py, weather.py, calc.py, hardware.py, system.py, settings.py, hotkeys.py
    ui/menubar.py, dock.py, desktop_icons.py, desktop_widgets.py, launchpad.py, spotlight.py,
       control_center.py, settings_dialog.py, widgets.py, glyphs.py, icons.py
