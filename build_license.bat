@echo off
chcp 65001 >nul
REM ============================================================
REM  ThingsWindows ?????? ?? ?? PyInstaller onefile ??
REM  ??: dist\ThingsWindows_license_generator.exe
REM  ??: ??, ? cmd ??? build_license.bat
REM ============================================================

cd /d "%~dp0"

echo ============================================================
echo   ?? ThingsWindows_license_generator.exe   (onefile, ????)
echo ============================================================

if exist build rmdir /s /q build
if exist dist\ThingsWindows_license_generator.exe del /q dist\ThingsWindows_license_generator.exe

python -m PyInstaller ^
    --onefile --windowed --noconfirm --clean ^
    --name "ThingsWindows_license_generator" ^
    --hidden-import win32crypt ^
    license_gui.py

if errorlevel 1 (
    echo.
    echo [X] ????!
    pause
    exit /b 1
)

echo.
echo ============================================================
echo   ? ????! ??: dist\ThingsWindows_license_generator.exe
echo ============================================================
dir dist\ThingsWindows_license_generator.exe
echo.
pause
