@echo off
REM ============================================================
REM  ThingsWindows License Generator - double-click launcher
REM  v2.5.11 edition (new signing secret, 2026-11-05)
REM  NOTE: keep this file ASCII-only, cmd mis-parses UTF-8 Chinese
REM  Opens packaged EXE first; falls back to source mode.
REM ============================================================
cd /d "%~dp0"

if exist "releases\license-tools\ThingsWindows_license_generator.exe" (
    start "" "releases\license-tools\ThingsWindows_license_generator.exe"
    exit /b 0
)

REM No packaged EXE found - run from source (needs local Python)
start "" pythonw.exe license_gui.py
