@echo off
setlocal EnableExtensions
cd /d "%~dp0"
title Trading C++ Engine Builder
chcp 65001 >nul 2>&1

set "NO_PAUSE=0"
if /i "%~1"=="--no-pause" set "NO_PAUSE=1"

if not exist ".venv\Scripts\python.exe" (
    echo ERROR: .venv was not found. Run install_windows.bat first.
    goto :error
)

set "VENV_PY=%CD%\.venv\Scripts\python.exe"

echo Preparing C++ build dependencies...
"%VENV_PY%" -m pip install --upgrade setuptools wheel pybind11 --prefer-binary
if errorlevel 1 goto :error

if exist "build" rmdir /s /q "build" 2>nul
for %%F in (trading_engine*.pyd trading_engine*.dll trading_engine*.lib trading_engine*.exp) do del /q "%%F" 2>nul

echo Compiling the pybind11 C++ engine...
"%VENV_PY%" setup.py build_ext --inplace
if errorlevel 1 goto :compiler_error

"%VENV_PY%" -c "import trading_engine; print('C++ engine:', trading_engine.engine_version())"
if errorlevel 1 goto :import_error

if exist ".env" "%VENV_PY%" "tools\set_env_value.py" ".env" "REQUIRE_CPP_ENGINE" "true"
echo C++ engine build completed.
if "%NO_PAUSE%"=="0" pause
exit /b 0

:compiler_error
echo ERROR: C++ compilation failed.
echo Install Visual Studio 2022 Build Tools and select:
echo   - Desktop development with C++
echo   - MSVC v143 x64/x86 build tools
echo   - Windows 10 or Windows 11 SDK
goto :error

:import_error
echo ERROR: The engine compiled but Python could not import it.
echo Confirm that Python is 64-bit and that the build matches Python 3.11.
goto :error

:error
if "%NO_PAUSE%"=="0" pause
exit /b 1
