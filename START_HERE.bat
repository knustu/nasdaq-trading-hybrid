@echo off
setlocal EnableExtensions
cd /d "%~dp0"
title Trading Customer Strategy - Start
chcp 65001 >nul 2>&1
if not exist ".venv\Scripts\python.exe" (
    call "install_windows.bat"
    if errorlevel 1 exit /b 1
)
call "run_app.bat"
