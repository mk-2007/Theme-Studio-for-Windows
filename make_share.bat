@echo off
cd /d "%~dp0"
title Building the shareable Setup file
echo Building ThemeStudio-Setup.exe (one single file to send to anyone)...
python -m pip install -q -r requirements.txt pyinstaller
python -m pip install -q -r requirements-optional.txt
python -m PyInstaller --noconfirm --clean --onefile --windowed --name ThemeStudio-Setup --icon "assets\theme_studio.ico" --add-data "themes;themes" --add-data "assets;assets" --hidden-import comtypes --hidden-import pycaw --hidden-import screen_brightness_control main.py
echo.
if exist "dist\ThemeStudio-Setup.exe" (
  echo DONE. Send this one file:  %CD%\dist\ThemeStudio-Setup.exe
  explorer /select,"%CD%\dist\ThemeStudio-Setup.exe"
) else (
  echo Build failed - scroll up for the error.
)
pause
