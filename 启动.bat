@echo off
chcp 65001 >nul
cd /d "%~dp0"

REM v1.2.1: 默认用 --noconsole 静默版, 无黑色弹窗
REM 如果需要调试日志, 直接看 dist\things_debug.log

REM 优先使用打好的 exe (静默版, 无弹窗)
if exist "dist\ThingsWindows.exe" (
    echo ============================================================
    echo   Things Windows  v1.2.1  [静默模式]
    echo   启动后无黑色弹窗, 后台运行
    echo   日志: dist\things_debug.log
    echo ============================================================
    start "" "dist\ThingsWindows.exe"
    echo.
    echo 服务已启动, 浏览器会自动打开 http://localhost:8765
    echo 如果浏览器没自动弹, 手动打开上面地址即可
    echo.
    echo 关闭方式: 任务管理器搜索 ThingsWindows -> 结束任务
    echo.
    timeout /t 3 >nul
    goto :eof
)

REM 没有 exe 则回退到 Python 源码 (调试用, 有控制台看日志)
if exist "app.py" (
    echo ============================================================
    echo   Things Windows  v1.2.1  [源码模式, 调试用]
    echo ============================================================
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
