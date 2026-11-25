@echo off
setlocal EnableExtensions
cd /d "%~dp0"
chcp 65001 >nul 2>&1
if not exist ".venv\Scripts\python.exe" (
    echo Run install_windows.bat first.
    pause
    exit /b 1
)
set "VENV_PY=%CD%\.venv\Scripts\python.exe"
"%VENV_PY%" -c "import trading_engine" >nul 2>&1
if errorlevel 1 (
    "%VENV_PY%" -m pytest -q --ignore="tests/test_hybrid_engine.py"
) else (
    "%VENV_PY%" -m pytest -q
)
if errorlevel 1 pause
