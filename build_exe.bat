@echo off
cd /d "%~dp0"
python -m pip install pyinstaller
python -m PyInstaller --noconfirm --clean --windowed --name ThemeStudio --icon "assets\theme_studio.ico" --add-data "themes;themes" --add-data "assets;assets" --hidden-import comtypes --hidden-import pycaw --hidden-import screen_brightness_control main.py
echo.
echo Built: dist\ThemeStudio\ThemeStudio.exe   (use install.bat to install it properly)
pause
