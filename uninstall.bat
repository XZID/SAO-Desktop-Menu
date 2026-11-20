@echo off
rem SAO Desktop Menu - by Arthur_Zid - Copyright (c) 2026 Arthur_Zid - MIT License (see LICENSE.txt)
rem Turns the SAO Desktop Menu off, puts the old wallpaper back and removes it from startup.
cd /d "%~dp0"
python "%~dp0launcher.py" --stop
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0setup-startup.ps1" -Remove
echo You can now delete this folder.
pause
