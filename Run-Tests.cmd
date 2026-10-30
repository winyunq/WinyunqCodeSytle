@echo off
setlocal
cd /d "%~dp0"
py -3 tools\run_tests.py
pause
