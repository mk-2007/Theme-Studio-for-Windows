@echo off
cd /d "%~dp0"
python -m pip install pyinstaller
python -m PyInstaller --noconfirm --onefile --windowed --name ThemeStudio --add-data "themes;themes" main.py
echo.
echo Done. Your app is in the "dist" folder: dist\ThemeStudio.exe
pause
