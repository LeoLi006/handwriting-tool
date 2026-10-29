@echo off
chcp 65001 >nul
setlocal enabledelayedexpansion
cd /d "%~dp0"

rem ============================================================
rem  Handwriting Converter - launcher
rem  Picks a REAL python, skipping the Microsoft Store stub
rem  (WindowsApps\python.exe, which just opens the Store).
rem  NOTE: this file must stay ASCII-only so cmd parses it
rem        correctly under any codepage.
rem ============================================================

set "PY="

rem 1) search PATH for python, skip the WindowsApps stub
for /f "delims=" %%i in ('where python 2^>nul') do (
    set "CAND=%%i"
    echo !CAND! | findstr /i "WindowsApps" >nul
    if errorlevel 1 if not defined PY set "PY=!CAND!"
)

rem 2) also try python3
if not defined PY (
    for /f "delims=" %%i in ('where python3 2^>nul') do (
        set "CAND=%%i"
        echo !CAND! | findstr /i "WindowsApps" >nul
        if errorlevel 1 if not defined PY set "PY=!CAND!"
    )
)

rem 3) fall back to local Anaconda
if not defined PY (
    if exist "D:\Users\lwz\anaconda3\python.exe" set "PY=D:\Users\lwz\anaconda3\python.exe"
)

if not defined PY (
    echo [ERROR] No usable Python found.
    echo         Install Python 3 and check "Add Python to PATH".
    pause
    exit /b 1
)

rem verify the selected python actually runs
"%PY%" -c "import sys" >nul 2>nul
if errorlevel 1 (
    echo [ERROR] Selected Python cannot run: %PY%
    pause
    exit /b 1
)

echo Using Python: %PY%

rem ---- check deps, auto-install if missing ----
"%PY%" -c "import handright, fontTools, PIL, tkinterdnd2, matplotlib" >nul 2>nul
if errorlevel 1 (
    echo Installing missing deps: handright / fonttools / pillow / tkinterdnd2 / matplotlib ...
    "%PY%" -m pip install -r requirements.txt
)

echo Starting Handwriting Converter ...
"%PY%" gui.py
if errorlevel 1 (
    echo.
    echo [TIP] The program exited with an error. See messages above.
    pause
)
endlocal
