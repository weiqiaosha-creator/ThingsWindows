# -*- coding: utf-8 -*-
"""
Things Windows —— 原生桌面窗口启动器 (v2.0.0)
================================================
用 pywebview (Windows WebView2) 把 Things Web 界面包成原生窗口。

架构:
  同一进程内:
    1. 先 import app 模块 (后端 HTTP server, 端口 55234)
    2. 在守护线程里启动后端 (serve_forever)
    3. 用 pywebview 创建原生窗口指向 http://localhost:55234
    4. 用户关闭窗口时退出, 后端线程自动随进程结束

运行:
  python main_window.py

打包 (单文件, 双击即开):
  python -m PyInstaller --noconfirm --clean --onefile --windowed ^
      --name ThingsWindows ^
      --add-data "index.html;." ^
      --collect-all pywebview ^
      main_window.py

产物: dist/ThingsWindows.exe (~16MB)
  ✅ 原生窗口, 有标题栏, 无浏览器地址栏
  ✅ 内嵌 WebView2 渲染
  ✅ 自动启动后端 HTTP 服务
  ✅ 关闭窗口自动清理
"""

import sys
import os
import threading
import time

# ---------- PyInstaller 兼容 ----------
if getattr(sys, 'frozen', False):
    # 打包后: 资源在 sys._MEIPASS, EXE 在 sys.executable 目录
    BASE_DIR = os.path.dirname(sys.executable)
    sys.path.insert(0, sys._MEIPASS)
else:
    BASE_DIR = os.path.dirname(os.path.abspath(__file__))
    sys.path.insert(0, BASE_DIR)

BACKEND_PORT = 55234


def start_backend_thread(port: int = BACKEND_PORT) -> None:
    """在守护线程里启动 app.py 的 HTTP server。"""
    import app as webapp  # noqa (延迟 import, 确保 sys.path 已设置)

    def _run():
        try:
            server = webapp._try_bind(port)
            actual_port = server.server_address[1]
            if actual_port != port:
                print(f"[backend] 端口 {port} 被占用, 实际使用 {actual_port}")
            webapp.DEFAULT_PORT = actual_port  # 同步更新
            print(f"[backend] HTTP 服务启动 → http://localhost:{actual_port}")
            server.serve_forever()
        except Exception as e:
            print(f"[backend] ❌ 启动失败: {e}")

    t = threading.Thread(target=_run, daemon=True, name="ThingsBackend")
    t.start()


def wait_for_backend(port: int = BACKEND_PORT, timeout: float = 10.0) -> bool:
    """等待后端就绪。"""
    import urllib.request
    deadline = time.time() + timeout
    # 端口可能被占用后自动 +1, 所以遍历几个端口
    for p in range(port, port + 5):
        deadline2 = time.time() + timeout / 5
        while time.time() < deadline2:
            try:
                urllib.request.urlopen(f"http://127.0.0.1:{p}/api/health", timeout=1)
                return True
            except Exception:
                time.sleep(0.3)
    return False


def main():
    import webview
    import app as webapp  # 拿到版本号常量

    print("=" * 50)
    print(f"  Things Windows v{webapp.DISPLAY_VERSION} —— 原生桌面版")
    print("=" * 50)

    # 1. 启动后端线程
    start_backend_thread(BACKEND_PORT)

    # 2. 等待就绪
    if not wait_for_backend(BACKEND_PORT, timeout=15):
        print("[main] ❌ 后端启动超时, 退出")
        return

    # 3. 找实际端口 (可能被 +1)
    import urllib.request
    actual_port = BACKEND_PORT
    for p in range(BACKEND_PORT, BACKEND_PORT + 5):
        try:
            urllib.request.urlopen(f"http://127.0.0.1:{p}/api/health", timeout=1)
            actual_port = p
            break
        except Exception:
            continue

    url = f"http://localhost:{actual_port}/?v={webapp.VERSION}"
    print(f"[main] ✅ 后端就绪: {url}")
    print("[main] 🪟 打开原生窗口...")

    # 4. 创建原生窗口 (版本号从 app.VERSION 动态取)
    webview.create_window(
        title=f"Things Windows v{webapp.DISPLAY_VERSION}",
        url=url,
        width=1280,
        height=800,
        min_size=(800, 600),
        text_select=True,
        confirm_close=True,
        background_color="#f5f5f7",
    )

    # 5. 启动事件循环 (阻塞直到用户关闭窗口)
    webview.start(debug=False)

    print("[main] 👋 用户关闭窗口, 进程退出")


if __name__ == "__main__":
    main()
