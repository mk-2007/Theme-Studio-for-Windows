# Security notes

Theme Studio runs with normal user privileges and sits close to the Windows shell (taskbar, desktop, a
low-level keyboard hook), so it is held to a higher bar than an ordinary app. This file records what was
checked, what was fixed, and what is still open.

## Never requires admin rights
`core/winapi.is_elevated()` can check, and nothing in the app asks for elevation. If Theme Studio is ever run
as Administrator, refuse to continue elevated (this is enforced in `main.py`) - an elevated instance would be
able to affect other users' sessions and is not what the app is designed for.

## Least privilege
- No admin/elevation is requested anywhere, at build or run time.
- No driver, service, or kernel component. Everything is a normal user-mode process.
- The keyboard hook (`core/winkey.py`) is a standard `WH_KEYBOARD_LL` hook - the same mechanism many
  legitimate utilities (e.g. window managers, language switchers) use. It runs in its own thread so it can
  never block real keyboard input, reads only *which key, up or down, and whether Windows marked it as
  synthetic*, and never logs, stores, or transmits key codes or text. It can be turned off in Settings.
- The Windows taskbar is hidden, not disabled or deleted - `restore_taskbar.bat`, the tray menu, or
  `--restore-taskbar` always bring it back, and a background guard process (`core/guard.py`) does this
  automatically if Theme Studio ever crashes.

## Input validation
- **Settings file** (`core/settings.py`): every key has a strict validator (type, range, length, allowed
  values). Unknown keys and values that fail validation are dropped silently rather than crashing or being
  trusted. Writes are atomic (temp file + rename) so a crash mid-write can't corrupt the file. A settings
  file larger than 1&nbsp;MB, or that fails to parse, is quarantined (renamed to `.corrupt.json`) instead of
  being read.
- **Calculator** (`core/calc.py`): parses with `ast.parse` and walks a fixed allow-list of node types -
  never `eval()`. Expression length, parenthesis depth and exponent size are bounded so it can't be used to
  hang the app or exhaust memory (`2**99999999999999` and 40+ nested parens are rejected before evaluation).
- **File and app names shown in the UI** (`core/textsafe.py`): stripped of control characters, bidi
  override/isolate characters (the "Trojan Source" trick that can make a filename look different from what
  it is) and zero-width characters before they are drawn.
- **Weather API responses** (`core/weather.py`): every field is type- and range-checked before use; the
  response body is capped at 512&nbsp;KB; redirects are refused if they leave HTTPS.

## Launching things safely
- `core/index.is_safe_launch_target()` only allows launching a `shell:AppsFolder\...` id (Store apps) or a
  path that actually exists on disk - never a raw device path (`\\.\PhysicalDriveN`), and never something
  built from unvalidated text.
- `core/system.is_allowed_uri()` restricts what Theme Studio will hand to the shell's `ShellExecute`: only
  `https://`, `ms-settings:`, the Recycle Bin, or an existing local path. `file:`, `javascript:`,
  `search-ms:` and other custom URI handlers are refused.
- The file-search index never follows symlinks or junctions (prevents link loops and escaping the intended
  folders) and only scans the user's own Desktop/Documents/Downloads/Pictures/Videos/Music.

## Process launching
- No `shell=True` anywhere in the codebase (confirmed by `bandit`, see below).
- Every built-in Windows tool (`taskkill`, `netsh`, `powershell`, `explorer`, `taskmgr`, `rundll32`,
  `shutdown`) is invoked by an absolute path under `%SystemRoot%\System32`
  (`core/syspath.py`), not by bare name - this closes PATH-hijacking, where a malicious executable earlier
  on `PATH` (or in the working directory) could otherwise be launched instead of the real tool.
- Windows DLLs (`user32`, `shell32`, `dwmapi`, `kernel32`, `ole32`, `gdi32`) are loaded with
  `LOAD_LIBRARY_SEARCH_SYSTEM32`, so a malicious same-named DLL placed next to the app can't be loaded
  instead of the real one ("DLL planting").
- The self-installer (`core/selfinstall.py`) never builds a PowerShell command line by string-concatenating
  a path; every path crosses into the script through an environment variable, so a file or folder name
  cannot break out of the script. Uninstall only ever deletes a path it has verified is exactly
  `%LocalAppData%\Programs\ThemeStudio`.

## Network
The only network calls are to `open-meteo.com` and `geocoding-api.open-meteo.com` for weather (both
HTTPS, no API key, no account, no telemetry). Nothing else in the app makes a network request. There is no
analytics, crash reporting, or update-check phoning home.

## What is deliberately not encrypted
Settings (dock pins, notes text, weather city, window positions) are stored as plain JSON in
`%APPDATA%\ThemeStudio`, the same way most desktop utilities store preferences. None of it is a secret
(no passwords, tokens, or credentials are ever requested or stored), so this is a conscious choice, not an
oversight.

## Testing
- `tests/test_security.py` - 23 unit tests covering the sanitizer, calculator, URI/launch allow-lists, the
  layout/overlap logic, and the keyboard-hook state machine (pure logic, no Windows needed - run with
  `pytest`, or double-click `run_tests.bat` on Windows, which also runs the two scans below).
- `bandit -r core ui main.py` - static analysis for common Python security mistakes. Current result:
  **0 medium/high-severity findings.**
- `pip-audit` - checks every pinned dependency against the public vulnerability databases. Current result:
  **no known vulnerabilities** in PyQt6, psutil, pycaw, comtypes, or screen-brightness-control.

## Known limitations (be aware of these)
- **Not code-signed.** Windows SmartScreen will show "Windows protected your PC" for the shared
  `ThemeStudio-Setup.exe` until it is signed with a paid code-signing certificate. This is expected for an
  unsigned indie app and is not itself a vulnerability, but it is a legitimate reason for a cautious user
  (or Microsoft's Store review) to pause.
- **The keyboard hook is a single global hook for one purpose** (detect a solo Windows-key tap and Ctrl+Esc).
  It is not a general-purpose key logger and cannot become one without a code change, but it is worth
  a careful look from anyone auditing the app, precisely because that *category* of code is sensitive.
  `core/winkey.py` is deliberately kept small and self-contained so it's easy to audit end to end.
- **Recoloring other apps' title bars** (`core/winstyle.py`) uses a documented DWM API
  (`DwmSetWindowAttribute`) on window handles enumerated the normal way; it does not inject code into other
  processes or read their memory.
