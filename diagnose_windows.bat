@echo off
setlocal EnableExtensions
cd /d "%~dp0"
title Trading App Diagnostics
chcp 65001 >nul 2>&1

echo ============================================================
echo WINDOWS DIAGNOSTICS
echo Folder: %CD%
echo Date: %DATE% %TIME%
echo ============================================================
echo.

echo [System Python]
where py 2>nul
where python 2>nul
py -3.11 -c "import sys,platform; print(sys.version); print(sys.executable); print(platform.architecture())" 2>nul
python -c "import sys,platform; print(sys.version); print(sys.executable); print(platform.architecture())" 2>nul

echo.
echo [Virtual environment]
if exist ".venv\Scripts\python.exe" (
    ".venv\Scripts\python.exe" -c "import sys,platform; print(sys.version); print(sys.executable); print(platform.architecture())"
    ".venv\Scripts\python.exe" -m pip --version
) else (
    echo .venv is missing.
)

echo.
echo [C++ engine]
if exist ".venv\Scripts\python.exe" (
    ".venv\Scripts\python.exe" -c "import trading_engine; print(trading_engine.engine_version())" 2>nul
    if errorlevel 1 echo trading_engine import FAILED
)

echo.
echo [Visual Studio locator]
if exist "%ProgramFiles(x86)%\Microsoft Visual Studio\Installer\vswhere.exe" (
    "%ProgramFiles(x86)%\Microsoft Visual Studio\Installer\vswhere.exe" -latest -products * -requires Microsoft.VisualStudio.Component.VC.Tools.x86.x64 -property installationPath
) else (
    echo vswhere.exe not found.
)

echo.
echo [Project files]
if exist "setup.py" (echo setup.py OK) else (echo setup.py MISSING)
if exist "requirements.txt" (echo requirements.txt OK) else (echo requirements.txt MISSING)
if exist ".env" (echo .env OK) else (echo .env MISSING)
if exist "install_result.txt" type "install_result.txt"

echo.
pause
