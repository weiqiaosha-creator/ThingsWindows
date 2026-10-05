@echo off
chcp 65001 >nul
cd /d "%~dp0"

REM 先检查有没有装好的 exe
if exist "dist\ThingsWindows.exe" (
    echo 正在启动 Things Windows ...
    start "" "dist\ThingsWindows.exe"
    goto :eof
)

REM 否则用 python 直接跑
python app.py
if errorlevel 1 (
    echo.
    echo ❌ 启动失败。请确认已安装 Python 3.8+
    pause
)
