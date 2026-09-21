# Theme Studio installer: builds ThemeStudio.exe, installs it for your user, adds shortcuts and start-with-Windows.
$ErrorActionPreference = "Continue"
$src = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $src
function Say($m) { Write-Host ">> $m" -ForegroundColor Cyan }
function New-Shortcut($path, $target, $arguments, $work, $icon) {
    $ws = New-Object -ComObject WScript.Shell
    $lnk = $ws.CreateShortcut($path)
    $lnk.TargetPath = $target
    if ($arguments) { $lnk.Arguments = $arguments }
    $lnk.WorkingDirectory = $work
    $lnk.IconLocation = $icon
    $lnk.Description = "Theme Studio"
    $lnk.Save()
}

Say "Checking Python"
$python = (Get-Command python -ErrorAction SilentlyContinue).Source
if (-not $python) {
    Write-Host "Python was not found. Install Python 3.10+ from python.org (tick 'Add python.exe to PATH'), then run this again." -ForegroundColor Red
    exit 1
}

Say "Stopping any running copy"
Get-Process ThemeStudio -ErrorAction SilentlyContinue | Stop-Process -Force
Start-Sleep -Milliseconds 800

Say "Installing libraries"
& python -m pip install --disable-pip-version-check -q -r requirements.txt
& python -m pip install --disable-pip-version-check -q -r requirements-optional.txt
if ($LASTEXITCODE -ne 0) { Write-Host "(optional volume/brightness packages could not be installed - continuing)" -ForegroundColor Yellow }
& python -m pip install --disable-pip-version-check -q pyinstaller

$dest = Join-Path $env:LOCALAPPDATA "Programs\ThemeStudio"
$exe = Join-Path $dest "ThemeStudio.exe"
$built = $false

Say "Building the app (a minute or two)"
& python -m PyInstaller --noconfirm --clean --windowed --name ThemeStudio --icon "assets\theme_studio.ico" --add-data "themes;themes" --add-data "assets;assets" --hidden-import comtypes --hidden-import pycaw --hidden-import screen_brightness_control main.py 2>&1 | Out-Null
$bundle = Join-Path $src "dist\ThemeStudio"
if (Test-Path (Join-Path $bundle "ThemeStudio.exe")) {
    Say "Installing to $dest"
    New-Item -ItemType Directory -Force -Path $dest | Out-Null
    robocopy $bundle $dest /MIR /NFL /NDL /NJH /NJS /NP | Out-Null
    $built = $true
}

if ($built) {
    $target = $exe; $arguments = ""; $work = $dest; $icon = $exe
} else {
    Write-Host "Could not build the .exe - using a windowless launcher instead." -ForegroundColor Yellow
    $pyw = (& python -c "import sys,os;print(os.path.join(os.path.dirname(sys.executable),'pythonw.exe'))").Trim()
    $target = $pyw; $arguments = "`"$(Join-Path $src 'main.py')`""; $work = $src
    $icon = Join-Path $src "assets\theme_studio.ico"
}

Say "Creating shortcuts"
New-Shortcut (Join-Path $env:APPDATA "Microsoft\Windows\Start Menu\Programs\Theme Studio.lnk") $target $arguments $work $icon
New-Shortcut (Join-Path ([Environment]::GetFolderPath("Desktop")) "Theme Studio.lnk") $target $arguments $work $icon

Say "Starting with Windows"
$command = "`"$target`""
if ($arguments) { $command += " $arguments" }
Set-ItemProperty -Path "HKCU:\Software\Microsoft\Windows\CurrentVersion\Run" -Name "ThemeStudio" -Value $command

Say "Launching Theme Studio"
if ($arguments) { Start-Process -FilePath $target -ArgumentList $arguments -WorkingDirectory $work }
else { Start-Process -FilePath $target -WorkingDirectory $work }

Write-Host ""
Write-Host "Done. Theme Studio now runs by itself (no terminal) and starts with Windows." -ForegroundColor Green
Write-Host "Open Settings any time by launching Theme Studio again from the Start menu or desktop."
Write-Host "If anything ever looks wrong: press Ctrl+Alt+Q, or run uninstall.bat."
