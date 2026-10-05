# -*- coding: utf-8 -*-
"""
Things Windows —— Web 界面后端
纯标准库 http.server, 无额外依赖。
启动后浏览器访问 http://localhost:8765

打包: pyinstaller --onefile --noconsole --name ThingsWindows --add-data "index.html;." app.py
      生成 dist/ThingsWindows.exe (双击即静默启动, 后台无控制台弹窗)
调试: python app.py 55555     (直接源码跑, 有控制台看日志)
"""

import json
import logging
import os
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse, parse_qs

# 修复 Windows GBK 编码问题
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

# ---------- 日志配置 ----------
# 日志文件在 exe / 源码同目录下, 方便排查
_LOG_DIR = os.path.dirname(os.path.abspath(sys.argv[0])) if getattr(sys, 'frozen', False) else os.path.dirname(os.path.abspath(__file__))
_LOG_FILE = os.path.join(_LOG_DIR, "things_debug.log")

_root_log = logging.getLogger()
_root_log.setLevel(logging.INFO)
# 统一格式: [时间] [级别] [模块] 消息
_fmt = logging.Formatter("[%(asctime)s] [%(levelname)s] %(message)s", datefmt="%H:%M:%S")

# 1. 文件 handler —— 始终启用
_fh = logging.FileHandler(_LOG_FILE, encoding="utf-8")
_fh.setFormatter(_fmt)
_root_log.addHandler(_fh)

# 2. 控制台 handler —— 有控制台才加 (PyInstaller --noconsole 时没有)
if sys.stderr and sys.stderr.fileno() > 0:
    try:
        _ch = logging.StreamHandler(sys.stderr)
        _ch.setFormatter(_fmt)
        _root_log.addHandler(_ch)
    except Exception:
        pass

# 禁止 noisy 库的日志
logging.getLogger("urllib3").setLevel(logging.WARNING)

_log = logging.getLogger("things.app")
_log.info(f"Things Windows v2.0.0 启动, 日志文件: {_LOG_FILE}")

# 允许直接运行时引用 things_cloud
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from things_cloud import (  # noqa: E402
    Things,
    ThingsClient,
    ThingsCloudError,
    build_task6_payload,
    new_uuid,
    ACTION_CREATED,
    SS_COMPLETED,
    SS_PENDING,
)


# ============================================================
# 会话状态 (内存中, 单用户)
# ============================================================

_session: dict = {}  # {"things": Things(...), "email": "..."}
_session_lock = threading.Lock()

STATIC_DIR = os.path.dirname(os.path.abspath(__file__))

# PyInstaller 打包后资源在 sys._MEIPASS
if getattr(sys, "frozen", False):
    STATIC_DIR = sys._MEIPASS

INDEX_HTML = os.path.join(STATIC_DIR, "index.html")


def _get_things() -> Things:
    with _session_lock:
        if "things" not in _session:
            raise RuntimeError("not authenticated")
        return _session["things"]


# ============================================================
# Handler
# ============================================================

class Handler(BaseHTTPRequestHandler):
    # ---- 通用 ----

    def log_message(self, fmt, *args):
        print(f"[HTTP] {args[0]}")

    def _send_json(self, data, status=200):
        body = json.dumps(data, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-cache")
        self.end_headers()
        self.wfile.write(body)

    def _send_error(self, msg, status=400):
        self._send_json({"ok": False, "error": msg}, status)

    def _read_body(self):
        length = int(self.headers.get("Content-Length", 0))
        raw = self.rfile.read(length) if length else b""
        try:
            return json.loads(raw.decode("utf-8")) if raw else {}
        except Exception:
            return {}

    # ---- GET ----

    def do_GET(self):
        parsed = urlparse(self.path)
        path = parsed.path
        qs = parse_qs(parsed.query)

        # 静态文件
        if path == "/" or path == "/index.html":
            self._serve_static(INDEX_HTML, "text/html")
            return
        if path.startswith("/static/"):
            fpath = os.path.join(STATIC_DIR, path.lstrip("/"))
            if os.path.isfile(fpath):
                ext = os.path.splitext(fpath)[1].lower()
                mime = {".js": "application/javascript", ".css": "text/css",
                        ".png": "image/png", ".svg": "image/svg+xml",
                        ".ico": "image/x-icon"}.get(ext, "application/octet-stream")
                self._serve_static(fpath, mime)
                return

        # API
        try:
            if path == "/api/health":
                self._send_json({"ok": True, "authenticated": "things" in _session})

            elif path == "/api/tasks/all":
                t = _get_things()
                self._send_json({"ok": True, "tasks": t.get_all_tasks()})

            elif path == "/api/tasks":
                list_name = (qs.get("list") or ["today"])[0]
                keyword = (qs.get("q") or [None])[0]
                t = _get_things()
                self._send_json({"ok": True, "tasks": t.get_tasks(list_name, keyword=keyword)})

            elif path == "/api/completed":
                t = _get_things()
                self._send_json({"ok": True, "tasks": t.get_completed()})

            elif path == "/api/dedupe/plan":
                from things_cloud import build_dedupe_plan
                t = _get_things()
                plan = build_dedupe_plan(t.get_all_tasks())
                self._send_json({"ok": True, "plan": plan})

            elif path == "/api/debug/full":
                # 返回完整 rebuilt state (不 filter) 的 st 分布
                t = _get_things()
                all_tasks = t.get_all_tasks()
                from collections import Counter
                st_codes = Counter(x.get("st_code") for x in all_tasks)
                schedules = Counter(x.get("schedule") for x in all_tasks)
                human = Counter(x.get("human_status") for x in all_tasks)
                samples = [x for x in all_tasks if any(
                    k in x.get("title", "")
                    for k in ["NAS", "洗车", "阳台", "计划您", "打开 Safari", "创建项目", "效率"]
                )]
                self._send_json({
                    "total": len(all_tasks),
                    "st_code_dist": {str(k): v for k, v in st_codes.items()},
                    "schedule_dist": dict(schedules),
                    "human_status_dist": dict(human),
                    "key_samples": samples[:25],
                })
            elif path == "/api/stats":
                # 返回各列表的任务数量 (一次请求全拿到)
                t = _get_things()
                from things_cloud import filter_tasks
                all_with_completed = t.get_all_tasks()
                pending = [x for x in all_with_completed if x["human_status"] == "pending"]
                counts = {
                    "inbox":     len(filter_tasks(pending, list_name="inbox")),
                    "today":     len(filter_tasks(pending, list_name="today")),
                    "projects":  len(filter_tasks(pending, list_name="projects")),
                    "anytime":   len(filter_tasks(pending, list_name="anytime")),
                    "someday":   len(filter_tasks(pending, list_name="someday")),
                    "all":       len(pending),
                    "logbook":   len([x for x in all_with_completed if x["human_status"] in ("completed","canceled")]),
                }
                self._send_json({"ok": True, "counts": counts})

            elif path == "/api/account":
                with _session_lock:
                    self._send_json({
                        "ok": True,
                        "email": _session.get("email", ""),
                        "authenticated": "things" in _session,
                    })

            elif path == "/api/debug/sync":
                # 诊断接口 —— 返回 raw history items 和重建结果
                t = _get_things()
                from collections import Counter
                from things_cloud import _rebuild_state
                raw_items, head_idx = t.client.sync_history_items(t.history_key, 0)
                rebuilt = _rebuild_state(raw_items)
                kinds = Counter(it.get("e", "?") for it in raw_items)
                actions = Counter(it.get("t", "?") for it in raw_items)
                all_fields = set()
                for it in raw_items:
                    all_fields.update(it.get("p", {}).keys())
                self._send_json({
                    "ok": True,
                    "raw_count": len(raw_items),
                    "head_index": head_idx,
                    "rebuilt_count": len(rebuilt),
                    "kind_dist": dict(kinds),
                    "action_dist": {str(k): v for k, v in actions.items()},
                    "payload_fields": sorted(all_fields),
                    "sample_raw": raw_items[:10],
                    "sample_rebuilt": rebuilt[:10],
                })

            else:
                self._send_error(f"unknown route: {path}", 404)

        except RuntimeError as e:
            self._send_error(str(e), 401)
        except ThingsCloudError as e:
            self._send_error(str(e), 502)
        except Exception as e:
            self._send_error(f"server error: {e}", 500)

    # ---- POST ----

    def do_POST(self):
        parsed = urlparse(self.path)
        path = parsed.path
        body = self._read_body()

        try:
            if path == "/api/auth":
                email = (body.get("email") or "").strip()
                password = body.get("password") or ""
                if not email or not password:
                    self._send_error("邮箱和密码不能为空")
                    return
                c = ThingsClient(email, password)
                info = c.verify()
                with _session_lock:
                    _session.clear()
                    _session["things"] = Things(email, password, info["history-key"])
                    _session["email"] = email
                self._send_json({
                    "ok": True,
                    "email": email,
                    "history_key": info["history-key"],
                    "message": "连接成功!",
                })

            elif path == "/api/logout":
                with _session_lock:
                    _session.clear()
                self._send_json({"ok": True})

            elif path == "/api/tasks":
                t = _get_things()
                uuid = t.add_task(
                    title=body.get("title", "").strip(),
                    notes=body.get("notes") or None,
                    when=body.get("when") or None,
                    deadline=body.get("deadline") or None,
                    tags=body.get("tags") or None,
                )
                self._send_json({"ok": True, "uuid": uuid})

            elif path == "/api/tasks/complete":
                t = _get_things()
                uuid = body.get("uuid", "")
                if not uuid:
                    self._send_error("需要 uuid")
                    return
                ok = mark_task_status(t, uuid, SS_COMPLETED)
                self._send_json({"ok": ok})

            elif path == "/api/tasks/trash":
                t = _get_things()
                uuid = body.get("uuid", "")
                if not uuid:
                    self._send_error("需要 uuid")
                    return
                ok = trash_task(t, uuid)
                self._send_json({"ok": ok})

            elif path == "/api/dedupe/apply":
                t = _get_things()
                remove_uuids = body.get("remove_uuids", [])
                if not remove_uuids:
                    self._send_json({"ok": True, "removed": 0})
                    return
                removed = trash_tasks_batch(t, remove_uuids)
                self._send_json({"ok": True, "removed": removed})

            else:
                self._send_error(f"unknown route: {path}", 404)

        except RuntimeError as e:
            self._send_error(str(e), 401)
        except ThingsCloudError as e:
            self._send_error(str(e), 502)
        except Exception as e:
            self._send_error(f"server error: {e}", 500)

    # ---- 静态服务 ----

    def _serve_static(self, fpath: str, mime: str):
        try:
            with open(fpath, "rb") as f:
                data = f.read()
            self.send_response(200)
            self.send_header("Content-Type", f"{mime}; charset=utf-8" if mime.startswith("text/") else mime)
            self.send_header("Content-Length", str(len(data)))
            self.send_header("Cache-Control", "no-cache")
            self.end_headers()
            self.wfile.write(data)
        except FileNotFoundError:
            self._send_error("not found", 404)


# ============================================================
# 任务操作辅助 (通过 commit 写回 Things Cloud)
# ============================================================

def _cache_lookup(things: Things, uuid: str):
    """在内存缓存里按 uuid 找任务 dict (供 commit 后即时修改)。"""
    if things._tasks is None:
        things.sync()
    for t in things._tasks:
        if t.get("uuid") == uuid:
            return t
    return None


def mark_task_status(things: Things, uuid: str, new_status: int) -> bool:
    """
    修改任务的 ss 状态 (完成/取消/恢复)。
    Things Cloud Task6 modify payload 必须带:
      - ss: 新状态
      - md: 修改日期 (秒级 Unix 时间戳)
      - sp: 完成日期 (仅 completed 时需要)
    """
    from things_cloud import SS_COMPLETED, SS_CANCELED, _things_now

    now_ts = _things_now()  # 秒级

    p = {
        "ss": new_status,
        "md": now_ts,
    }
    # completed 时带 sp (completion date)
    if new_status == SS_COMPLETED:
        p["sp"] = now_ts

    if things._head_index is None:
        head = things.client.get_history_head(things.history_key)
        things._head_index = head.get("latest-server-index", 0)
    ancestor = things._head_index

    item = {"uuid": uuid, "e": "Task6", "t": 1, "p": p}
    new_head = things.client.commit(things.history_key, [item], ancestor)
    things._head_index = new_head

    # 即时更新本地缓存
    t = _cache_lookup(things, uuid)
    if t is not None:
        if new_status == SS_COMPLETED:
            t["human_status"] = "completed"
        elif new_status == SS_CANCELED:
            t["human_status"] = "canceled"
        else:
            t["human_status"] = "pending"
        t["status"] = new_status
    return True


def trash_task(things: Things, uuid: str) -> bool:
    """把任务扔进垃圾桶 (带 md 修改日期)。"""
    from things_cloud import _things_now
    now_ts = _things_now()

    if things._head_index is None:
        head = things.client.get_history_head(things.history_key)
        things._head_index = head.get("latest-server-index", 0)
    ancestor = things._head_index

    item = {
        "uuid": uuid,
        "e": "Task6",
        "t": 1,
        "p": {"tr": True, "md": now_ts},
    }
    new_head = things.client.commit(things.history_key, [item], ancestor)
    things._head_index = new_head

    if things._tasks is not None:
        things._tasks = [t for t in things._tasks if t.get("uuid") != uuid]
    return True


def trash_tasks_batch(things: Things, uuids: list[str]) -> int:
    """批量扔进垃圾桶 (带 md)。"""
    from things_cloud import _things_now
    now_ts = _things_now()

    if things._head_index is None:
        head = things.client.get_history_head(things.history_key)
        things._head_index = head.get("latest-server-index", 0)
    ancestor = things._head_index

    items = []
    for u in uuids:
        items.append({
            "uuid": u,
            "e": "Task6",
            "t": 1,
            "p": {"tr": True, "md": now_ts},
        })
    new_head = things.client.commit(things.history_key, items, ancestor)
    things._head_index = new_head

    if things._tasks is not None:
        things._tasks = [t for t in things._tasks if t.get("uuid") not in uuids]
    return len(uuids)


# ============================================================
# 启动
# ============================================================

def _try_bind(preferred: int, max_tries: int = 20) -> ThreadingHTTPServer:
    """尝试绑定端口, 被占用则自动 +1。"""
    for offset in range(max_tries):
        port = preferred + offset
        try:
            return ThreadingHTTPServer(("127.0.0.1", port), Handler)
        except OSError as e:
            if offset == max_tries - 1:
                raise
            print(f"⚠  端口 {port} 被占用, 尝试 {port + 1}...")


DEFAULT_PORT = 55234

def main(port: int = DEFAULT_PORT, open_browser: bool = True):
    server = _try_bind(port)
    port = server.server_address[1]
    url = f"http://localhost:{port}"
    print("=" * 60)
    print(f"  🚀 Things Windows 已启动 → {url}")
    print(f"  📂 服务目录: {STATIC_DIR}")
    print("  ⚠  请勿关闭此窗口 (关闭则停止服务)")
    print("=" * 60)

    if open_browser:
        try:
            import webbrowser
            webbrowser.open(url)
        except Exception:
            pass

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n👋 已停止")
        server.shutdown()


if __name__ == "__main__":
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8765
    main(port=port)
