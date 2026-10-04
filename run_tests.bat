@echo off
cd /d "%~dp0"
python -m pip install -q -r requirements.txt -r requirements-dev.txt
echo.
echo === Unit tests ===
python -m pytest tests -v
echo.
echo === Security scan (bandit) ===
python -m bandit -r core ui main.py -ll
echo.
echo === Dependency vulnerability check ===
python -m pip_audit -r requirements.txt
pause
