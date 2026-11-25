@echo off
setlocal EnableExtensions
cd /d "%~dp0"
title Trading Customer Strategy
chcp 65001 >nul 2>&1

if not exist ".venv\Scripts\python.exe" (
    echo The application is not installed yet. Starting installer...
    call "install_windows.bat"
    if errorlevel 1 exit /b 1
)

set "VENV_PY=%CD%\.venv\Scripts\python.exe"

"%VENV_PY%" -c "import trading_engine" >nul 2>&1
if errorlevel 1 (
    echo C++ engine is missing. Attempting one repair build...
    call "build_cpp.bat" --no-pause
    if errorlevel 1 (
        echo C++ build is unavailable. Starting with Python fallback.
        if not exist ".env" copy /y ".env.example" ".env" >nul
        "%VENV_PY%" "tools\set_env_value.py" ".env" "REQUIRE_CPP_ENGINE" "false"
    )
)

"%VENV_PY%" "main.py"
set "APP_EXIT=%ERRORLEVEL%"
if not "%APP_EXIT%"=="0" (
    echo.
    echo Application exited with error code %APP_EXIT%.
    echo Run diagnose_windows.bat for environment details.
    pause
)
exit /b %APP_EXIT%
