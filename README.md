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

## Share it with someone (one file)
1. Double-click **`make_share.bat`** on your PC (once, after your changes). It builds `dist\ThemeStudio-Setup.exe`.
2. Send that single file (Google Drive / OneDrive link works best; email and WhatsApp often block .exe files).
3. They double-click it and press **Install**. No Python needed. It installs, adds shortcuts, starts with Windows.
   Windows may show "Windows protected your PC": click *More info* -> *Run anyway* (the app is not code-signed).
   Uninstall: tray icon -> Uninstall Theme Studio.

## Desktop style: macOS and Ubuntu (Linux) sections
Settings -> Desktop style has one tab per mode. Each tab is fully self-contained and remembered on its own:
- **Appearance**: Dark / Light / Match Windows
- **App icons**: native Windows icons or rounded "plate" icons
- **Widgets**: which of Weather/Clock/System/Calendar/Notes show in that mode, and their transparency
- **Wallpaper**: pick an image and how it fits; optionally swap the Windows wallpaper when you switch to that mode
"Switch to _ now" jumps straight to that mode. Nothing here needs the dock or tray - it is one screen.

## Security
See `SECURITY.md` for the full write-up. In short: no admin rights ever, every setting read from disk is
validated before use, no `shell=True` anywhere, every system tool is launched by absolute path (no PATH
hijacking), Windows DLLs load from System32 only (no DLL planting), the calculator never uses `eval`, and
the only network calls are HTTPS to the weather API. `run_tests.bat` runs the unit tests plus two security
scanners (bandit, pip-audit); both currently come back clean.

## Publishing (Microsoft Store / Play Store) - read this first
- **Google Play** is for Android apps only. Theme Studio is a Windows desktop app, so it cannot go on Play
  Store; that store is not applicable here.
- **Microsoft Store** technically accepts Win32 apps packaged as MSIX, but Store policy restricts apps that
  alter core shell behavior. Theme Studio hides the taskbar, hooks the Windows key globally, and repositions
  other apps' windows - the same category of app as Rainmeter or Wallpaper Engine's shell integrations,
  none of which are on the Store. A Store submission in its current form is likely to be rejected, and MSIX
  packaging would require replacing the self-installer and startup-registry code with the Store's app
  APIs. Realistic distribution for this kind of app is direct download (what `make_share.bat` already
  produces) or a `winget` package (`winget install` - no store review, still a clean one-command install).
  I can prepare a winget manifest, or a reduced "widgets and themes only" edition with no shell
  replacement that would have a real shot at Store approval, if you want either.

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
