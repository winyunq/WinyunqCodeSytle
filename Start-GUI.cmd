@echo off
setlocal
cd /d "%~dp0"
where py >nul 2>nul
if errorlevel 1 (
  python Run.py gui
) else (
  py -3 Run.py gui
)
if errorlevel 1 pause
