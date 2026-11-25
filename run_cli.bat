@echo off
setlocal EnableExtensions
cd /d "%~dp0"
chcp 65001 >nul 2>&1
if not exist ".venv\Scripts\python.exe" (
    call "install_windows.bat"
    if errorlevel 1 exit /b 1
)
"%CD%\.venv\Scripts\python.exe" "cli.py"
if errorlevel 1 pause
