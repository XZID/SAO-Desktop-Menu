@echo off
rem SAO Desktop Menu - by Arthur_Zid - Copyright (c) 2026 Arthur_Zid - MIT License (see LICENSE.txt)
rem SAO Desktop Menu - one-time setup
cd /d "%~dp0"
echo.
echo  SAO Desktop Menu setup  -  by Arthur_Zid
echo  ======================
where python >/dev/null 2>nul
if errorlevel 1 (
  echo  Python is not installed.
  echo  1. Get it from https://www.python.org/downloads/
  echo  2. In the installer, tick "Add python.exe to PATH"
  echo  3. Run this install.bat again
  pause
  exit /b 1
)
echo  Installing the one extra Python package it needs (Pillow)...
python -m pip install --user --quiet --disable-pip-version-check pillow
echo.
choice /c YN /m " Start it automatically every time you log in"
if not errorlevel 2 powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0setup-startup.ps1"
echo.
choice /c YN /m " Play the LINK START intro animation when the PC starts"
if errorlevel 2 (python "%~dp0launcher.py" --set intro=false >nul) else (python "%~dp0launcher.py" --set intro=true >nul)
echo.
echo  Starting it now. On an empty spot of the desktop, HOLD the middle mouse
echo  button (scroll wheel) and DRAG DOWN a little to open the menu.
start "" pythonw "%~dp0launcher.py"
echo.
pause
