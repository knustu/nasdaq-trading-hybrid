@echo off
setlocal EnableExtensions
cd /d "%~dp0"
title Trading App Installer
chcp 65001 >nul 2>&1

echo ============================================================
echo Trading Customer Strategy - Windows Installer v2.0.1
echo Project folder: %CD%
echo ============================================================
echo.

if not exist "setup.py" goto :not_extracted
if not exist "requirements.txt" goto :not_extracted

set "PY_LAUNCHER="
where py >nul 2>&1
if not errorlevel 1 (
    py -3.11 -c "import sys; raise SystemExit(0 if sys.version_info[:2] == (3, 11) and sys.maxsize ^> 2**32 else 1)" >nul 2>&1
    if not errorlevel 1 set "PY_LAUNCHER=py -3.11"
)

if not defined PY_LAUNCHER (
    where python >nul 2>&1
    if not errorlevel 1 (
        python -c "import sys; raise SystemExit(0 if sys.version_info[:2] == (3, 11) and sys.maxsize ^> 2**32 else 1)" >nul 2>&1
        if not errorlevel 1 set "PY_LAUNCHER=python"
    )
)

if not defined PY_LAUNCHER goto :python_error

echo [1/6] Python launcher: %PY_LAUNCHER%

if exist ".venv" if not exist ".venv\Scripts\python.exe" (
    echo Incomplete virtual environment found. Recreating it...
    rmdir /s /q ".venv" 2>nul
)

if not exist ".venv\Scripts\python.exe" (
    echo [2/6] Creating virtual environment...
    %PY_LAUNCHER% -m venv ".venv"
    if errorlevel 1 goto :venv_error
) else (
    echo [2/6] Existing virtual environment found.
)

set "VENV_PY=%CD%\.venv\Scripts\python.exe"
if not exist "%VENV_PY%" goto :venv_error

"%VENV_PY%" -c "import sys; print('Python:', sys.version); print('Executable:', sys.executable)"
if errorlevel 1 goto :venv_error

echo.
echo [3/6] Updating installer packages...
"%VENV_PY%" -m pip install --upgrade pip setuptools wheel pybind11 --prefer-binary
if errorlevel 1 goto :pip_error

echo.
echo [4/6] Installing Python dependencies...
"%VENV_PY%" -m pip install -r "requirements.txt" --prefer-binary
if errorlevel 1 goto :dependency_error

if not exist ".env" copy /y ".env.example" ".env" >nul

echo.
echo [5/6] Building C++ engine...
call "build_cpp.bat" --no-pause
if errorlevel 1 goto :cpp_fallback

"%VENV_PY%" "tools\set_env_value.py" ".env" "REQUIRE_CPP_ENGINE" "true"
set "CPP_OK=1"
goto :run_tests

:cpp_fallback
echo.
echo WARNING: C++ engine build failed.
echo The application will be configured to use the Python fallback temporarily.
echo Install Visual Studio Build Tools with Desktop development with C++
echo and run build_cpp.bat later to enable the hybrid C++ engine.
"%VENV_PY%" "tools\set_env_value.py" ".env" "REQUIRE_CPP_ENGINE" "false"
set "CPP_OK=0"

:run_tests
echo.
echo [6/6] Running verification tests...
if "%CPP_OK%"=="1" (
    "%VENV_PY%" -m pytest -q
) else (
    "%VENV_PY%" -m pytest -q --ignore="tests/test_hybrid_engine.py"
)
if errorlevel 1 goto :test_error

>"install_result.txt" echo INSTALL_OK
>>"install_result.txt" echo Python=%VENV_PY%
>>"install_result.txt" echo CppEngine=%CPP_OK%
>>"install_result.txt" echo Date=%DATE% %TIME%

echo.
echo ============================================================
echo Installation completed successfully.
if "%CPP_OK%"=="1" (
    echo C++ engine: ENABLED
) else (
    echo C++ engine: PYTHON FALLBACK - build_cpp.bat can repair it later.
)
echo Run run_app.bat or START_HERE.bat.
echo ============================================================
pause
exit /b 0

:not_extracted
echo ERROR: Project files were not found next to this installer.
echo Use "Extract All" on the ZIP file, then run this BAT inside the extracted folder.
goto :failed

:python_error
echo ERROR: 64-bit Python 3.11 was not found.
echo Install Python 3.11 x64 and enable "Add Python to PATH".
goto :failed

:venv_error
echo ERROR: Failed to create or open .venv.
echo Delete the .venv folder and run this installer again.
goto :failed

:pip_error
echo ERROR: pip/setuptools installation failed.
echo Check the internet connection and antivirus permissions.
goto :failed

:dependency_error
echo ERROR: Python dependency installation failed.
echo Run diagnose_windows.bat and inspect the command output above.
goto :failed

:test_error
echo ERROR: Verification tests failed.
echo The packages were installed, but the project needs the error above to be fixed.
goto :failed

:failed
>"install_result.txt" echo INSTALL_FAILED
>>"install_result.txt" echo Date=%DATE% %TIME%
echo.
echo Installation failed. This window will stay open so the error can be read.
pause
exit /b 1
