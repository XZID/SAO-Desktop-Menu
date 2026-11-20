@echo off
rem SAO Desktop Menu - by Arthur_Zid - Copyright (c) 2026 Arthur_Zid - MIT License (see LICENSE.txt)
rem Stops the SAO live desktop and brings back your normal wallpaper.
cd /d "%~dp0"
python "%~dp0launcher.py" --stop
timeout /t 2 >nul
