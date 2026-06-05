@echo off
title Yuketang PPT Downloader
cd /d "%~dp0"

echo ======================================
echo   Yuketang PPT Downloader
echo ======================================
echo.

set PYTHON=
py --version >nul 2>&1 && set PYTHON=py
if "%PYTHON%"=="" python --version >nul 2>&1 && set PYTHON=python
if "%PYTHON%"=="" (
    echo Python not found.
    echo Please install Python 3.8+ from:
    echo https://www.python.org/downloads/
    echo IMPORTANT: check [Add Python to PATH]
    start https://www.python.org/downloads/
    pause
    exit /b 1
)

echo [1/3] Installing dependencies...
%PYTHON% -m pip install requests Pillow -q 2>nul
if %errorlevel% neq 0 (
    echo [WARN] pip failed, trying to continue...
)

echo [2/3] Setting up Playwright...
%PYTHON% -m pip install playwright -q 2>nul
%PYTHON% -m playwright install chromium 2>nul

echo [3/3] Starting...
echo.
%PYTHON% gui.py
pause
