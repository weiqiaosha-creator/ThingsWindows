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

# ============================================================
# 🔖 版本号 — 只改这里, 保持三处一致
# ============================================================
VERSION = "2.5.10"           # 内部版本 (精确到 patch)
DISPLAY_VERSION = "2.5"      # 用户可见 (只保留前两位, 比如 "2.5" 版) — v2.5.10: 版本护栏, 上报版本/schema 永久钳制在手机端基准 (32208/301) 以内, Windows 迭代不再触发手机端更新提示
APP_NAME = "Things Windows"

import auth_store  # noqa: E402  — 安全凭证存储 (DPAPI + 设备指纹 + 2FA)
import lic  # noqa: E402  — 授权码验证 (机器码 + HMAC + 有效期)

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
_log.info(f"{APP_NAME} v{VERSION} (显示 v{DISPLAY_VERSION}) 启动, 日志文件: {_LOG_FILE}")

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
    SS_CANCELED,
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
            fname = path[len("/static/"):]
            # 源码模式: STATIC_DIR/vue.global.prod.js
            # PyInstaller: STATIC_DIR/static/vue.global.prod.js (datas 目标是 static/)
            fpath = os.path.join(STATIC_DIR, fname)
            if not os.path.isfile(fpath):
                fpath = os.path.join(STATIC_DIR, "static", fname)
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
                self._send_json({
                    "ok": True,
                    "authenticated": "things" in _session,
                    "version": VERSION,
                    "display_version": DISPLAY_VERSION,
                    "app_name": APP_NAME,
                })

            elif path == "/api/remembered":
                # 前端启动时检查: 这台电脑记住了账号吗?
                info = auth_store.has_remembered()
                self._send_json({"ok": True, **info})

            elif path == "/api/tasks/all":
                t = _get_things()
                self._send_json({"ok": True, "tasks": t.get_all_tasks()})

            elif path == "/api/tasks":
                list_name = (qs.get("list") or ["today"])[0]
                keyword = (qs.get("q") or [None])[0]
                tag_filter = (qs.get("tag") or [None])[0]
                t = _get_things()
                all_t = t.get_all_tasks()
                # tag 过滤: 不限 list, 只要有 tag 就返回 (非 trash)
                if tag_filter:
                    from things_cloud import filter_tasks
                    tasks = filter_tasks(all_t, only_pending=False, tag_filter=tag_filter)
                else:
                    tasks = t.get_tasks(list_name, keyword=keyword)
                self._send_json({"ok": True, "tasks": tasks})

            elif path == "/api/tags":
                # 返回所有标签 + 每个标签的任务数
                t = _get_things()
                self._send_json({"ok": True, "tags": t.get_tags()})

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
                    "trash":     len([x for x in all_with_completed if x.get("trashed")]),
                }
                self._send_json({"ok": True, "counts": counts})

            elif path == "/api/account":
                with _session_lock:
                    self._send_json({
                        "ok": True,
                        "email": _session.get("email", ""),
                        "authenticated": "things" in _session,
                    })

            elif path == "/api/license":
                # 当前授权状态
                self._send_json(lic.check_local_license())

            elif path == "/api/machine-code":
                # 返回本机机器码 (发给授权方生成授权码)
                self._send_json({"ok": True, "machine_code": lic.get_machine_code()})

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
                remember = body.get("remember", False)
                pin = (body.get("pin") or "").strip() or None
                if not email or not password:
                    self._send_error("邮箱和密码不能为空")
                    return
                # 授权门禁: 未激活不能登录
                lic_info = lic.check_local_license()
                if not lic_info.get("ok"):
                    self._send_json({
                        "ok": False,
                        "error": "请先激活授权码才能使用 (登录页底部授权区输入)",
                        "license_required": True,
                    })
                    return
                c = ThingsClient(email, password)
                info = c.verify()
                with _session_lock:
                    _session.clear()
                    _session["things"] = Things(email, password, info["history-key"])
                    _session["email"] = email

                # 记住密码 (DPAPI + 设备指纹 + 可选 PIN)
                if remember:
                    try:
                        auth_store.save_credentials(email, password, pin=pin)
                    except Exception as e:
                        logging.getLogger("things").warning(f"保存凭证失败: {e}")

                self._send_json({
                    "ok": True,
                    "email": email,
                    "history_key": info["history-key"],
                    "message": "连接成功!",
                })

            elif path == "/api/auth-2fa":
                # 用二次验证 PIN 登录 (从本机存储解密密码)
                pin = (body.get("pin") or "").strip()
                if not pin:
                    self._send_error("请输入二次验证密码")
                    return
                # 授权门禁
                lic_info = lic.check_local_license()
                if not lic_info.get("ok"):
                    self._send_json({"ok": False, "error": "授权已失效, 请重新激活", "license_required": True})
                    return
                rec = auth_store.load_credentials()
                if not rec:
                    self._send_error("本机没有记住的凭证 (可能换电脑了)")
                    return
                if rec["2fa_enabled"] and not auth_store.verify_2fa(pin):
                    self._send_error("二次验证密码错误")
                    return
                # 登录成功!
                c = ThingsClient(rec["email"], rec["password"])
                info = c.verify()
                with _session_lock:
                    _session.clear()
                    _session["things"] = Things(rec["email"], rec["password"], info["history-key"])
                    _session["email"] = rec["email"]
                self._send_json({
                    "ok": True,
                    "email": rec["email"],
                    "history_key": info["history-key"],
                    "message": "连接成功!",
                })

            elif path == "/api/remove-remembered":
                # 删除本机存储的凭证 (忘记 / 换账号)
                auth_store.remove_credentials()
                self._send_json({"ok": True})

            elif path == "/api/logout":
                with _session_lock:
                    _session.clear()
                self._send_json({"ok": True})

            elif path == "/api/license/activate":
                # 激活授权码
                key = (body.get("license") or "").strip()
                if not key:
                    self._send_error("请输入授权码")
                    return
                info = lic.parse_license(key)
                if info["ok"]:
                    lic.save_license(key)
                    self._send_json({
                        "ok": True,
                        "message": "授权成功 ✅",
                        "expiry_date": info["expiry_date"],
                        "is_permanent": info["is_permanent"],
                        "days_remaining": info["days_remaining"],
                    })
                else:
                    self._send_json({
                        "ok": False,
                        "error": info["reason"],
                    })

            elif path == "/api/license/revoke":
                # 清除本机授权
                lic.clear_license()
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
                # 兼容旧端点 — 硬编码设为 completed
                t = _get_things()
                uuid = body.get("uuid", "")
                if not uuid:
                    self._send_error("需要 uuid")
                    return
                ok = mark_task_status(t, uuid, SS_COMPLETED)
                self._send_json({"ok": ok})

            elif path == "/api/tasks/status":
                # v2.5.8: 通用状态端点 — pending/completed/canceled
                t = _get_things()
                uuid = body.get("uuid", "")
                status_str = (body.get("status") or "").lower().strip()
                if not uuid:
                    self._send_error("需要 uuid")
                    return
                status_map = {"pending": SS_PENDING, "completed": SS_COMPLETED, "canceled": SS_CANCELED}
                if status_str not in status_map:
                    self._send_error(f"status 必须是 {list(status_map.keys())} 之一")
                    return
                ok = mark_task_status(t, uuid, status_map[status_str])
                self._send_json({"ok": ok})

            elif path == "/api/tasks/trash":
                t = _get_things()
                uuid = body.get("uuid", "")
                if not uuid:
                    self._send_error("需要 uuid")
                    return
                ok = trash_task(t, uuid)
                self._send_json({"ok": ok})

            elif path == "/api/tasks/move":
                # 任务跨分类移动 (改 st/sr)
                t = _get_things()
                uuid = body.get("uuid", "")
                target = body.get("target", "inbox")
                if not uuid:
                    self._send_error("需要 uuid")
                    return
                try:
                    ok = move_task_schedule(t, uuid, target)
                    self._send_json({"ok": ok})
                except ValueError as e:
                    self._send_error(str(e))

            elif path == "/api/tasks/modify":
                # v2.5.7: 通用字段修改 (标题/备注/标签/效期)
                t = _get_things()
                uuid = body.get("uuid", "")
                fields = body.get("fields", {}) or body
                # 兼容两种传法: {uuid, fields: {...}} 或 {uuid, tt, nt, tg, dd}
                if "fields" not in body and isinstance(fields, dict):
                    fields = {k: v for k, v in body.items() if k not in ("uuid",)}
                if not uuid:
                    self._send_error("需要 uuid")
                    return
                try:
                    result = modify_task_fields(t, uuid, fields)
                    self._send_json(result)
                except ValueError as e:
                    self._send_error(str(e))

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
# v2.5.7: 通用任务字段修改 (标题/备注/标签/效期)
# ============================================================

def _get_reverse_tag_map(things) -> dict[str, str]:
    """
    扫描 Things Cloud 原始条目, 构建 {中文名: Tag4 uuid} 反向映射。
    用于前端传入中文名 → 后端转 UUID 写回 Task6.tg。
    """
    try:
        raw, _ = things.client.sync_history_items(things.history_key, 0)
        rev = {}
        for item in raw:
            if item.get("e") == "Tag4":
                p = item.get("p", {})
                name = p.get("tt") or p.get("ti") or ""
                if name:
                    rev[name] = item["uuid"]
        return rev
    except Exception:
        return {}


def modify_task_fields(things: Things, uuid: str, fields: dict) -> dict:
    """
    通用 Task6 字段修改。fields 可包含:
      tt       → 标题 (str)
      nt       → 备注 (str)
      tg       → 标签 (list[str], 中文名, 空列表=清空标签)
      dd       → 效期 (str YYYY-MM-DD | None=清空 | ""=清空)
    返回 {ok: bool, changed: list[str]}
    """
    from things_cloud import _things_now, _date_to_ts

    if not fields:
        return {"ok": False, "changed": []}

    if things._head_index is None:
        head = things.client.get_history_head(things.history_key)
        things._head_index = head.get("latest-server-index", 0)
    ancestor = things._head_index
    now_ts = _things_now()

    p: dict = {"md": now_ts}

    changed = []

    # 标题
    if "tt" in fields:
        val = (fields["tt"] or "").strip()
        if val:
            p["tt"] = val
            p["ti"] = val   # 双写, Things Cloud 兼容
            changed.append("title")

    # 备注
    if "nt" in fields:
        val = fields["nt"] or ""
        p["nt"] = val
        changed.append("notes")

    # 标签 (中文名列表 → UUID 列表)
    if "tg" in fields:
        names = fields["tg"] or []
        rev = _get_reverse_tag_map(things)
        uuid_list = []
        not_found = []
        for name in names:
            name = (name or "").strip()
            if not name:
                continue
            if name in rev:
                uuid_list.append(rev[name])
            else:
                not_found.append(name)
        p["tg"] = uuid_list
        changed.append("tags")
        # 未知标签不阻塞, 但记日志
        if not_found:
            print(f"[modify] 未匹配到 Tag4: {not_found}")

    # 效期
    if "dd" in fields:
        val = fields["dd"]
        if not val:
            # 清空效期 → 用 0 (或直接不写 p)
            # Things Cloud Task6 修改, 不写 dd 即保留原值; 写 0 表示清空
            p["dd"] = 0
            changed.append("deadline")
        else:
            try:
                ts = _date_to_ts(str(val).strip())
                p["dd"] = ts
                changed.append("deadline")
            except Exception:
                raise ValueError(f"效期格式错误, 需 YYYY-MM-DD: {val}")

    if len(p) == 1 and "md" in p:
        # 只有 md → 没改东西
        return {"ok": True, "changed": []}

    item = {"uuid": uuid, "e": "Task6", "t": 1, "p": p}
    new_head = things.client.commit(things.history_key, [item], ancestor)
    things._head_index = new_head

    # 即时更新本地缓存
    t = _cache_lookup(things, uuid)
    if t is not None:
        if "tt" in p:
            t["title"] = p["tt"]
        if "nt" in p:
            t["notes"] = p.get("nt", "")
        if "tg" in p:
            # 反向还原: UUID→中文名
            raw2, _ = things.client.sync_history_items(things.history_key, 0)
            tag_map = {}
            for it in raw2:
                if it.get("e") == "Tag4":
                    name = (it.get("p") or {}).get("tt") or ""
                    if name:
                        tag_map[it["uuid"]] = name
            t["tags"] = [tag_map.get(u, u) for u in p["tg"]]
        if "dd" in p:
            if p["dd"]:
                t["deadline_ms"] = p["dd"]
                try:
                    from datetime import datetime as _dt
                    if abs(float(p["dd"])) > 1e12:
                        t["deadline_date"] = _dt.fromtimestamp(float(p["dd"]) / 1000).strftime("%Y-%m-%d")
                    else:
                        t["deadline_date"] = _dt.fromtimestamp(float(p["dd"])).strftime("%Y-%m-%d")
                except Exception:
                    pass
            else:
                t["deadline_ms"] = None
                t["deadline_date"] = ""

    return {"ok": True, "changed": changed}


def move_task_schedule(things: Things, uuid: str, target: str) -> bool:
    """
    修改任务的调度 (st + sr), 实现"移动分类"。
    target 可选值:
      'inbox'       → st=0 (收件箱, 无日期)
      'today'       → st=1 + sr=今天
      'tomorrow'    → st=2 + sr=明天
      'anytime'     → st=1 (随时/日程)
      'someday'     → st=2 (某天/以后)
      'YYYY-MM-DD'  → st=2 + sr=指定日期
    Things Cloud Task6 modify 必须带 md (修改日期, 秒级)。
    """
    from things_cloud import ST_INBOX, ST_ANYTIME, ST_SOMEDAY, _things_now, _date_to_ts
    from datetime import datetime, timedelta

    now_ts = _things_now()

    # 解析 target → (st, sr_ts_or_None)
    target_lc = (target or "").lower().strip()
    if target_lc in ("inbox", ""):
        st_val, sr_val = ST_INBOX, None
    elif target_lc == "today":
        st_val = ST_ANYTIME
        sr_val = _date_to_ts(datetime.now().strftime("%Y-%m-%d"))
    elif target_lc == "tomorrow":
        st_val = ST_SOMEDAY
        tmr = datetime.now() + timedelta(days=1)
        sr_val = _date_to_ts(tmr.strftime("%Y-%m-%d"))
    elif target_lc in ("anytime", "scheduled"):
        st_val, sr_val = ST_ANYTIME, None
    elif target_lc in ("someday", "upcoming"):
        st_val, sr_val = ST_SOMEDAY, None
    else:
        # 尝试 YYYY-MM-DD
        try:
            st_val = ST_SOMEDAY
            sr_val = _date_to_ts(target_lc)
        except Exception:
            raise ValueError(f"未知 target: {target}")

    p = {"st": st_val, "md": now_ts}
    if sr_val is not None:
        p["sr"] = sr_val
    # inbox 明确清空 sr
    if st_val == ST_INBOX:
        p["sr"] = 0

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
        from things_cloud import ST_INBOX, ST_ANYTIME, ST_SOMEDAY
        st_map = {ST_INBOX: "inbox", ST_ANYTIME: "anytime", ST_SOMEDAY: "someday"}
        t["st_code"] = st_val
        t["schedule"] = st_map.get(st_val, "inbox")
        if sr_val is not None:
            t["scheduled_ms"] = sr_val
            try:
                from datetime import datetime as _dt
                if abs(float(sr_val)) > 1e12:
                    t["scheduled_date"] = _dt.fromtimestamp(float(sr_val) / 1000).strftime("%Y-%m-%d")
                else:
                    t["scheduled_date"] = _dt.fromtimestamp(float(sr_val)).strftime("%Y-%m-%d")
            except Exception:
                pass
        elif st_val == ST_INBOX:
            t["scheduled_ms"] = None
            t["scheduled_date"] = ""
    return True


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

