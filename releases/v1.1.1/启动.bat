@echo off
chcp 65001 >nul
cd /d "%~dp0"

echo ============================================================
echo   Things Windows  v1.1.2
echo   (基于 Things Cloud 官方同步协议)
echo ============================================================
echo.

REM 优先使用打好的 exe
if exist "dist\ThingsWindows.exe" (
    echo [1/1] 正在启动 ThingsWindows.exe ...
    echo       启动后会自动弹出浏览器窗口
    echo       关闭本窗口 = 停止服务
    echo.
    start "" "dist\ThingsWindows.exe"
    timeout /t 3 >nul
    goto :eof
)

REM 没有 exe 则回退到 Python 源码
if exist "app.py" (
    echo [fallback] 未找到 exe, 使用 Python 源码启动 ...
    python app.py
    if errorlevel 1 (
        echo.
        echo [X] 启动失败, 请确认已安装 Python 3.8+
        pause
    )
    goto :eof
)

echo [X] 未找到 dist\ThingsWindows.exe 或 app.py
echo     请检查文件是否完整
pause


