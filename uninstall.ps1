# Removes Theme Studio and puts the normal Windows taskbar and desktop icons back.
$ErrorActionPreference = "Continue"
$dest = Join-Path $env:LOCALAPPDATA "Programs\ThemeStudio"
$exe = Join-Path $dest "ThemeStudio.exe"

Get-Process ThemeStudio -ErrorAction SilentlyContinue | Stop-Process -Force
Start-Sleep -Milliseconds 800
if (Test-Path $exe) { & $exe --restore-taskbar }
else {
    $src = Split-Path -Parent $MyInvocation.MyCommand.Path
    & python (Join-Path $src "main.py") --restore-taskbar
}
Remove-ItemProperty -Path "HKCU:\Software\Microsoft\Windows\CurrentVersion\Run" -Name "ThemeStudio" -ErrorAction SilentlyContinue
Remove-Item (Join-Path $env:APPDATA "Microsoft\Windows\Start Menu\Programs\Theme Studio.lnk") -ErrorAction SilentlyContinue
Remove-Item (Join-Path ([Environment]::GetFolderPath("Desktop")) "Theme Studio.lnk") -ErrorAction SilentlyContinue
if (Test-Path $dest) { Remove-Item -Recurse -Force $dest }
Write-Host "Theme Studio removed. Your settings are kept in %APPDATA%\ThemeStudio (delete that folder to erase them)."
