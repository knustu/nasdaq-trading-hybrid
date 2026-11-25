@echo off
setlocal EnableExtensions
cd /d "%~dp0"
chcp 65001 >nul 2>&1
if not exist ".venv\Scripts\python.exe" (
    echo Run install_windows.bat first.
    pause
    exit /b 1
)
"%CD%\.venv\Scripts\python.exe" "verify_hybrid.py"
if errorlevel 1 pause
