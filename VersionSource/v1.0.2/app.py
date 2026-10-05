"""
Things Windows v1.0.2 —— Web 界面后端
纯标准库 http.server, 无额外依赖。
启动后浏览器访问 http://localhost:8765

架构：单文件 HTTP server + things_cloud.py 独立模块
版本时间线：v1.0.2 (2026-10-04)
"""

import json
import os
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse, parse_qs

# Windows 终端 utf-8
if sys.platform == 'win32':
    sys.stdout.reconfigure(encoding='utf-8')
    sys.stderr.reconfigure(encoding='utf-8')

# 项目根目录
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# 从 things_cloud 模块导入（v1.0.2 已有独立模块）
from things_cloud import (
    Things, ThingsClient, ThingsCloudError,
    build_task6_payload, new_uuid,
    ACTION_CREATED, SS_COMPLETED, SS_PENDING,
)

# ============ 全局状态 ============

_session: dict = {}               # email -> Things 客户端
_session_lock = threading.Lock()

STATIC_DIR = os.path.dirname(os.path.abspath(__file__))
if getattr(sys, 'frozen', False):   # PyInstaller 打包后
    STATIC_DIR = sys._MEIPASS
INDEX_HTML = os.path.join(STATIC_DIR, 'index.html')


# ============ Helpers ============

def _get_things() -> Things:
    """从 session 获取当前登录的 Things 对象。"""
    with _session_lock:
        if not _session:
            raise ThingsCloudError('not authenticated')
        # v1.0.2 单账号模式, 取第一个
        return next(iter(_session.values()))


# ============ Task 操作 ============

def mark_task_status(uuid: str, new_status: str):
    """修改任务的 ss 状态 (完成/取消/恢复)。
    latest-server-index + Task6/Task7 分支。"""
    tc = _get_things().client
    commit = tc.begin_commit()
    commit.add_mark_done(uuid, new_status)
    return tc.commit(commit)


def trash_task(uuid: str):
    """把任务扔进垃圾桶 (tr=true)。"""
    tc = _get_things().client
    commit = tc.begin_commit()
    commit.add_trash(uuid)
    return tc.commit(commit)


def trash_tasks_batch(uuids: list):
    """批量扔进垃圾桶。一次 commit。"""
    tc = _get_things().client
    commit = tc.begin_commit()
    for u in uuids:
        commit.add_trash(u)
    return tc.commit(commit)


# ============ HTTP Handler ============

class Handler(BaseHTTPRequestHandler):

    def log_message(self, fmt, *args):
        print(f"[HTTP] {self.address_string()} - {fmt % args}")

    def _send_json(self, data: dict, status=200):
        body = json.dumps(data, ensure_ascii=False).encode('utf-8')
        self.send_response(status)
        self.send_header('Content-Type', 'application/json; charset=utf-8')
        self.send_header('Content-Length', str(len(body)))
        self.send_header('Cache-Control', 'no-cache')
        self.end_headers()
        self.wfile.write(body)

    def _send_error(self, msg: str, status=400):
        self._send_json({'error': msg}, status)

    def _read_body(self) -> dict:
        length = int(self.headers.get('Content-Length', 0))
        raw = self.rfile.read(length) if length else b''
        return json.loads(raw.decode('utf-8')) if raw else {}

    # ---------- GET ----------

    def do_GET(self):
        parsed = urlparse(self.path)
        path = parsed.path
        qs = parse_qs(parsed.query)

        # 静态文件
        if path == '/index.html' or path == '/':
            return self._serve_static('index.html', 'text/html')
        if path.startswith('/static/'):
            fname = path[len('/static/'):]
            return self._serve_static(fname)

        try:
            if path == '/api/health':
                return self._send_json({'status': 'ok', 'port': 8765})

            if path == '/api/tasks/all':
                t = _get_things()
                return self._send_json({'tasks': t.get_all_tasks()})

            if path == '/api/tasks':
                # ?list=today
                list_type = qs.get('list', ['today'])[0]
                t = _get_things()
                return self._send_json({'tasks': t.filter_tasks(list_type)})

            if path == '/api/completed':
                t = _get_things()
                all_tasks = t.get_all_tasks()
                done = [x for x in all_tasks if x.get('human_status') == 'completed']
                return self._send_json({'tasks': done})

            if path == '/api/dedupe/plan':
                t = _get_things()
                return self._send_json({'plan': t.plan_deduplicate()})

            if path == '/api/debug/full':
                t = _get_things()
                all_tasks = t.get_all_tasks()
                return self._send_json({
                    'total': len(all_tasks),
                    'pending': [x for x in all_tasks if x.get('human_status') == 'pending'],
                    'done': [x for x in all_tasks if x.get('human_status') == 'completed'],
                })

            if path == '/api/account':
                t = _get_things()
                return self._send_json({'email': t.email})

            if path == '/api/debug/sync':
                t = _get_things()
                head = t.client.get_head_index()
                return self._send_json({'head_index': head})

            self._send_error(f'unknown route: {path}', 404)

        except ThingsCloudError as e:
            self._send_error(str(e))
        except Exception as e:
            self._send_error(f'server error: {e}', 500)

    # ---------- POST ----------

    def do_POST(self):
        parsed = urlparse(self.path)
        path = parsed.path
        body = self._read_body()

        try:
            if path == '/api/auth':
                email = body.get('email', '').strip()
                password = body.get('password', '')
                if not email or not password:
                    return self._send_error('邮箱和密码不能为空')
                client = ThingsClient(email, password)
                client.login()
                with _session_lock:
                    _session[email] = Things(client, email)
                return self._send_json({
                    'ok': True,
                    'email': email,
                    'history-key': client.history_key,
                    'msg': '连接成功!',
                })

            if path == '/api/logout':
                with _session_lock:
                    _session.clear()
                return self._send_json({'ok': True})

            if path == '/api/tasks':
                t = _get_things()
                payload = build_task6_payload(
                    uuid=new_uuid(),
                    title=body.get('title', ''),
                    notes=body.get('notes', ''),
                    schedule=body.get('when'),
                    deadline=body.get('deadline'),
                    tags=body.get('tags', []),
                    action=ACTION_CREATED,
                )
                t.client.commit_simple([payload])
                return self._send_json({'ok': True, 'uuid': payload['uuid']})

            if path == '/api/tasks/complete':
                uuid = body.get('uuid')
                if not uuid:
                    return self._send_error('需要 uuid')
                mark_task_status(uuid, SS_COMPLETED)
                return self._send_json({'ok': True})

            if path == '/api/tasks/trash':
                uuid = body.get('uuid')
                trash_task(uuid)
                return self._send_json({'ok': True})

            if path == '/api/dedupe/apply':
                uuids = body.get('remove_uuids', [])
                trash_tasks_batch(uuids)
                return self._send_json({'ok': True, 'removed': len(uuids)})

            self._send_error(f'unknown route: {path}', 404)

        except ThingsCloudError as e:
            self._send_error(str(e))
        except Exception as e:
            self._send_error(f'server error: {e}', 500)

    # ---------- 静态文件 ----------

    def _serve_static(self, fname: str, mime=None):
        fpath = os.path.join(STATIC_DIR, fname)
        if not os.path.exists(fpath):
            return self._send_error('not found', 404)
        ext = os.path.splitext(fname)[1].lower()
        mime_map = {
            '.html': 'text/html', '.js': 'application/javascript',
            '.css': 'text/css', '.png': 'image/png',
            '.svg': 'image/svg+xml', '.ico': 'image/x-icon',
        }
        mime = mime or mime_map.get(ext, 'application/octet-stream')
        if mime.startswith('text/'):
            mime += '; charset=utf-8'
        data = open(fpath, 'rb').read()
        self.send_response(200)
        self.send_header('Content-Type', mime)
        self.send_header('Content-Length', str(len(data)))
        self.send_header('Cache-Control', 'no-cache')
        self.end_headers()
        self.wfile.write(data)


# ============ Port binding ============

def _try_bind(port: int, preferred=8765, max_tries=10):
    """尝试绑定端口, 被占用则自动 +1。"""
    import socket
    for p in range(preferred, preferred + max_tries):
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            s.bind(('127.0.0.1', p))
            s.close()
            return p
        except OSError:
            print(f'⚠  端口 {p} 被占用, 尝试 {p+1} ...')
    raise RuntimeError(f'无法找到空闲端口 ({preferred}-{preferred+max_tries})')


# ============ main ============

def main():
    port = _try_bind(8765)
    server = ThreadingHTTPServer(('127.0.0.1', port), Handler)

    print('=' * 60)
    print(f'  🚀 Things Windows 已启动 → http://localhost:{port}')
    print(f'  📂 服务目录: {STATIC_DIR}')
    print('  ⚠  请勿关闭此窗口 (关闭则停止服务)')
    print('=' * 60)
    print()

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print('\n👋 已停止')
        server.server_close()


if __name__ == '__main__':
    main()
