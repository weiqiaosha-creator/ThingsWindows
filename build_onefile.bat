@echo off
chcp 65001 >nul
REM ============================================================
REM  Things Windows ?? ?? PyInstaller ?????
REM  ??: dist\ThingsWindows_vX.Y.Z.exe
REM  ??: ??, ? cmd ??? build_onefile.bat
REM ============================================================

cd /d "%~dp0"

REM 1. ? app.py ??? VERSION
for /f "usebackq tokens=2 delims==\"" %%a in (indstr /c:"VERSION = " app.py) do set VERSION=%%a
set VERSION=%VERSION: =%
if "%VERSION%"=="" (
    echo [X] ??? VERSION, ??? app.py
    pause
    exit /b 1
)
set EXE_NAME=ThingsWindows_v%VERSION%

echo ============================================================
echo   ?? %EXE_NAME%.exe   (onefile, ????, pywebview ????)
echo ============================================================

REM 2. ????
if exist build rmdir /s /q build
if exist dist\*.exe del /q dist\*.exe

REM 3. PyInstaller onefile
python -m PyInstaller ^
    --onefile --windowed --noconfirm --clean ^
    --name "%EXE_NAME%" ^
    --add-data "index.html;." ^
    --collect-all webview ^
    --hidden-import pythonnet ^
    --hidden-import clr ^
    --hidden-import Bottle ^
    --hidden-import requests ^
    --hidden-import win32crypt ^
    main_window.py

if errorlevel 1 (
    echo.
    echo [X] ????!
    pause
    exit /b 1
)

REM 4. ????
echo.
echo ============================================================
echo   ? ????!
echo   ??: dist\%EXE_NAME%.exe
echo ============================================================
dir dist\%EXE_NAME%.exe
echo.
pause
