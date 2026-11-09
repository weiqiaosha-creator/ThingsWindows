@echo off
REM ============================================================
REM  ThingsWindows License Generator - one-click build script
REM  v2.5.11 edition (new signing secret, 2026-11-05)
REM  NOTE: keep this file ASCII-only, cmd mis-parses UTF-8 Chinese
REM
REM  Flow: PyArmor obfuscate license_gui.py + lic.py + lic_secret.py
REM        -> PyInstaller onefile -> deploy to releases\license-tools\
REM  Output: dist\ThingsWindows_license_generator.exe
REM ============================================================
cd /d "%~dp0"

echo [1/4] PyArmor obfuscate sources (protect signing secret) ...
pyarmor gen -O obf_gui -r license_gui.py lic.py lic_secret.py
if errorlevel 1 (
    echo [X] PyArmor obfuscation FAILED!
    pause
    exit /b 1
)

echo [2/4] PyInstaller build (onefile, windowed) ...
pyinstaller --onefile --windowed --noconfirm --clean ^
    --name "ThingsWindows_license_generator" ^
    --paths obf_gui ^
    --hidden-import lic ^
    --hidden-import lic_secret ^
    --hidden-import pyarmor_runtime_000000 ^
    obf_gui\license_gui.py
if errorlevel 1 (
    echo.
    echo [X] PyInstaller build FAILED!
    pause
    exit /b 1
)

echo [3/4] Sanity check: generate + verify a license in obfuscated code ...
pushd obf_gui
python -c "import lic; k = lic.generate_license(lic.get_machine_code()); v = lic.parse_license(k); assert v['ok'], 'verify failed'; print('core check OK')"
popd
if errorlevel 1 (
    echo [X] Core check FAILED - NOT deploying!
    pause
    exit /b 1
)

echo [4/4] Deploy to releases\license-tools\ ...
if not exist "releases\license-tools" mkdir "releases\license-tools"
copy /y "dist\ThingsWindows_license_generator.exe" "releases\license-tools\" >nul

echo.
echo ============================================================
echo   DONE. Output: releases\license-tools\ThingsWindows_license_generator.exe
echo ============================================================
dir "releases\license-tools\ThingsWindows_license_generator.exe"
echo.
pause
