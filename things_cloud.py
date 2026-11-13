# -*- coding: utf-8 -*-
"""
Things Cloud API — Python 跨平台客户端
直接通过 Cultured Code 的 Things Cloud 服务同步任务数据。
参考: github.com/arthursoares/things-cloud-sdk (MIT License)
      github.com/evanpurkhiser/things3-cloud (MIT License)
"""

import base64
import io
import json
import logging
import os
import re
import uuid as uuid_mod
from datetime import datetime, timezone, timedelta

import requests

# 日志 —— 默认输出到 stderr；app.py 启动时会重定向到文件
_log = logging.getLogger("things")

# ============================================================
# 常量
# ============================================================

API_ENDPOINT = "https://cloud.culturedcode.com"

# =====================================================================
# 🔒 版本护栏 (v2.5.10) — 永久镜像手机端基准, 不论 Windows 怎么迭代
#
# 手机端受 iOS 16.2 限制, 最高只能装 Things 3.22.8 且无法再升级。
# 手机端"其他端版本更高, 需要更新"弹窗由云端记录的客户端版本/schema
# 信息触发, Windows 端是唯一可控的上报方 —— 只要把上报值永久钳制在
# 手机端基准以内, Windows 后续任何迭代都不可能再触发该弹窗。
#
# 手机端永久基准 (Things 3.22.8 / iOS 16.2):
#   PHONE_VERSION_CEILING = "32208"   5位编码: 主(1) + 次(2) + 补丁(2)
#   PHONE_SCHEMA_CEILING  = "301"     手机端 3.22.x 支持的 schema
#
# 将来手机端若真升级了, 只需同步上调这两个基准值。
# 下面的上报候选值想怎么改都行, _enforce_version_guard() 会在 import
# 时自动把超过基准的值压回并写警告日志 —— 结构性保证, 不靠人记。
#
# EntityType: Task6 (服务端 E2E 验证可正常读写)
# =====================================================================

PHONE_VERSION_CEILING = "32208"   # 手机端版本编码上限 (永久基准)
PHONE_SCHEMA_CEILING = "301"      # 手机端 schema 上限 (永久基准)

# 上报候选值 (超过基准会被护栏自动压回)
THINGS_VERSION_CODE = "32208"           # iPhone Things 3.22.8 (5位编码)
SCHEMA_HEADER = "301"                   # 服务端 latest-schema-version=301


def _enforce_version_guard():
    """import 时强制钳制: 任何超过手机端基准的配置自动压回 + 记日志。"""
    global THINGS_VERSION_CODE, SCHEMA_HEADER
    try:
        if int(THINGS_VERSION_CODE) > int(PHONE_VERSION_CEILING):
            _log.warning(
                "版本护栏: THINGS_VERSION_CODE=%s 超过手机端基准 %s, 已自动压回",
                THINGS_VERSION_CODE, PHONE_VERSION_CEILING,
            )
            THINGS_VERSION_CODE = PHONE_VERSION_CEILING
        if int(SCHEMA_HEADER) > int(PHONE_SCHEMA_CEILING):
            _log.warning(
                "版本护栏: SCHEMA_HEADER=%s 超过手机端基准 %s, 已自动压回",
                SCHEMA_HEADER, PHONE_SCHEMA_CEILING,
            )
            SCHEMA_HEADER = PHONE_SCHEMA_CEILING
    except ValueError:
        _log.warning(
            "版本护栏: 版本值非法 (%r / %r), 重置为手机端基准",
            THINGS_VERSION_CODE, SCHEMA_HEADER,
        )
        THINGS_VERSION_CODE = PHONE_VERSION_CEILING
        SCHEMA_HEADER = PHONE_SCHEMA_CEILING


_enforce_version_guard()

THINGS_USER_AGENT = f"ThingsiPhone/{THINGS_VERSION_CODE}"   # ThingsiPhone/32208
THINGS_APP_ID = "com.culturedcode.ThingsiPhone"
THINGS_APP_INSTANCE_ID = (
    "000000000000000000000000000000000000000000000000000000000000000-"
    f"{THINGS_APP_ID}-"
    "000000000000000000000000000000000000000000000000000000000000000"
)

# Schedule 字段 (st)
ST_INBOX = 0        # Inbox
ST_ANYTIME = 1      # Anytime / Today (需要配合 sr 日期)
ST_SOMEDAY = 2      # Someday / Upcoming

# Status 字段 (ss)
SS_PENDING = 0
SS_CANCELED = 2
SS_COMPLETED = 3

# Item Kind
KIND_TASK6 = "Task6"  # 服务端 E2E 验证兼容 (iPhone 3.22.x)
KIND_TASK7 = "Task7"
KIND_AREA = "Area3"
KIND_TAG = "Tag4"
KIND_CHECKLIST = "ChecklistItem3"
KIND_TOMBSTONE = "Tombstone2"

# Action (t)
ACTION_CREATED = 0
ACTION_MODIFIED = 1


# ============================================================
# Base58 编解码 (Bitcoin alphabet)
# ============================================================

BASE58_ALPHABET = "123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz"


def _b58encode(data: bytes) -> str:
    """将任意字节串编码为 Base58 字符串。"""
    # 计算前导 0x00 字节数量 -> 对应前导 '1'
    zeros = 0
    for b in data:
        if b == 0:
            zeros += 1
        else:
            break
    # 大整数转换
    n = int.from_bytes(data, "big")
    if n == 0:
        return "1" * zeros
    result = []
    while n > 0:
        n, mod = divmod(n, 58)
        result.append(BASE58_ALPHABET[mod])
    # 前导 1 + 反转
    return ("1" * zeros) + "".join(reversed(result))


def _b58decode(s: str) -> bytes:
    """将 Base58 字符串解码为原始字节串。"""
    zeros = 0
    for c in s:
        if c == "1":
            zeros += 1
        else:
            break
    n = 0
    for c in s[zeros:]:
        idx = BASE58_ALPHABET.find(c)
        if idx < 0:
            raise ValueError(f"Invalid Base58 char: {c!r}")
        n = n * 58 + idx
    if n == 0:
        return b"\x00" * zeros
    # 计算需要多少字节
    byte_len = (n.bit_length() + 7) // 8
    raw = n.to_bytes(byte_len, "big")
    return b"\x00" * zeros + raw


def new_uuid() -> str:
    """生成 Things Cloud 兼容的 Base58 UUID。"""
    u = uuid_mod.uuid4()
    return _b58encode(u.bytes)


def validate_uuid(s: str) -> bool:
    """验证 Base58 UUID 合法性 (必须解码为恰好 16 字节)。"""
    try:
        raw = _b58decode(s)
        return len(raw) == 16
    except Exception:
        return False


# ============================================================
# 时间工具
# ============================================================

# =====================================================================
# 时间戳说明 (来自 Go SDK arthursoares/things-cloud-sdk)
# Things Cloud 的 Timestamp 使用"秒级 Unix 时间戳" (带小数, float64)
# 例如: cd=1495662927.014228, sr=1495584000, tir=1495584000
# =====================================================================

def _things_now() -> float:
    """Things Cloud 使用的秒级 Unix 时间戳 (UTC, 带小数)。"""
    return datetime.now(timezone.utc).timestamp()


def _date_to_ts(ymd: str) -> float:
    """
    将 YYYY-MM-DD 转换为 Things Cloud 使用的秒级时间戳。
    v2.5.13: 对齐官方客户端口径 — 日期统一存 UTC 零点。
    实测: 北京用户手机上排"2026-11-09", 官方写 sr=1794182400 (=UTC 零点, 北京 08:00)。
    旧版写本地零点, 与官方差 8 小时。
    """
    dt = datetime.strptime(ymd, "%Y-%m-%d").replace(tzinfo=timezone.utc)
    epoch = datetime(1970, 1, 1, tzinfo=timezone.utc)
    return float((dt - epoch).total_seconds())


def _resolve_when(when: str) -> tuple[int, float | None]:
    """
    将 Things URL Scheme 风格的 when 值解析为 (st, sr_ts) 元组。
    when: 'today' | 'evening' | 'tomorrow' | 'anytime' | 'someday' | 'inbox' | 'YYYY-MM-DD'
    返回的 sr_ts 是秒级 Unix 时间戳 (float)。
    """
    today = datetime.now()
    if when in ("inbox", None):
        return ST_INBOX, None
    elif when in ("anytime", "Today", "today", "evening", "This Evening"):
        return ST_ANYTIME, _date_to_ts(today.strftime("%Y-%m-%d"))
    elif when in ("tomorrow",):
        tmr = today + timedelta(days=1)
        return ST_SOMEDAY, _date_to_ts(tmr.strftime("%Y-%m-%d"))
    elif when in ("someday", "Someday"):
        return ST_SOMEDAY, None
    else:
        # 尝试解析为 YYYY-MM-DD
        try:
            return ST_SOMEDAY, _date_to_ts(when)
        except ValueError:
            return ST_ANYTIME, _date_to_ts(today.strftime("%Y-%m-%d"))


# ============================================================
# 客户端
# ============================================================

class ThingsCloudError(Exception):
    pass


class ThingsClient:
    """Things Cloud HTTP 客户端。"""

    # 🚨 终极伪装: 完全复刻 iPhone Things 3.22.8
    # iPhone 看到 history 里有 ThingsiPhone/32208 (与本机 3.22.8 一致) → 认为是"同版本同平台" → 不弹更新!
    CLIENT_INFO = {
        "dm": "iPhone14,2",           # iPhone 13 Pro (常见设备型号)
        "lr": "CN",
        "nf": True,
        "nk": True,
        "nn": "ThingsiPhone",
        "nv": THINGS_VERSION_CODE,    # "32208" — 5位编码 3.22.8 (与手机一致)
        "on": "iOS",
        "ov": "16.2",                  # 精确匹配你的 iPhone iOS 版本
        "pl": "zh-CN",
        "ul": "zh-Hans-CN",
    }

    def __init__(self, email: str, password: str, endpoint: str = API_ENDPOINT):
        self.email = email
        self.password = password
        self.endpoint = endpoint
        self.session = requests.Session()
        self.session.timeout = 30

    # ---------- HTTP 底层 ----------

    def _headers(self, extra: dict | None = None) -> dict:
        headers = {
            "Host": "cloud.culturedcode.com",
            "User-Agent": THINGS_USER_AGENT,
            "Accept": "application/json",
            "Accept-Charset": "UTF-8",
            "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
            "Authorization": f"Password {self.password}",
            "Content-Type": "application/json; charset=UTF-8",
            "Content-Encoding": "UTF-8",
            "Things-Client-Info": base64.b64encode(
                json.dumps(self.CLIENT_INFO, separators=(",", ":")).encode()
            ).decode(),
            # ✅ Schema header —— 所有请求都要带 (Go SDK + Rust SDK 统一做法)
            "Schema": SCHEMA_HEADER,
            "App-Id": THINGS_APP_ID,
            "App-Instance-Id": THINGS_APP_INSTANCE_ID,
        }
        if extra:
            headers.update(extra)
        return headers

    def _get(self, path: str, params: dict | None = None) -> requests.Response:
        return self.session.get(
            f"{self.endpoint}{path}",
            headers=self._headers(),
            params=params,
        )

    def _post(self, path: str, body: dict, extra_headers: dict | None = None, params: dict | None = None) -> requests.Response:
        h = self._headers(extra_headers)
        return self.session.post(
            f"{self.endpoint}{path}",
            headers=h,
            params=params,
            data=json.dumps(body).encode(),
        )

    # ---------- 账号 / 认证 ----------

    history_key: str | None = None

    def verify(self) -> dict:
        """验证凭据有效，返回账户信息。
        Rust SDK authenticate() 直接从这里拿 history-key — 不需要额外 endpoint!
        """
        resp = self._get(f"/version/1/account/{self.email}")
        if resp.status_code == 401:
            raise ThingsCloudError("认证失败 — 邮箱或密码错误")
        if resp.status_code != 200:
            raise ThingsCloudError(f"Verify 失败: HTTP {resp.status_code} {resp.text[:200]}")
        data = resp.json()
        # ✅ 从 verify 响应里拿 history-key (Rust SDK authenticate())
        self.history_key = data.get("history-key") or data.get("uuid")
        return data

    # ---------- History ----------

    def get_history_keys(self) -> list[str]:
        """返回 history key (Rust SDK 只有一个, 从 verify 响应里拿)。"""
        if not self.history_key:
            self.verify()  # verify 会自动设 self.history_key
        return [self.history_key] if self.history_key else []

    def get_history_head(self, history_key: str) -> dict:
        """获取 history 元数据 (latest-server-index 等)。"""
        resp = self._get(f"/version/1/history/{history_key}")
        if resp.status_code != 200:
            raise ThingsCloudError(f"获取 history 头失败: HTTP {resp.status_code}")
        return resp.json()

    def sync_history_items(self, history_key: str, start_index: int = 0) -> tuple[list, int]:
        """
        拉取自 start_index 以来所有 history items。
        返回 (all_items, current_head_index)。
        """
        all_items = []
        cursor = start_index
        current_head = cursor

        while True:
            resp = self._get(
                f"/version/1/history/{history_key}/items",
                params={"start-index": cursor},
            )
            if resp.status_code != 200:
                raise ThingsCloudError(f"Sync items 失败: HTTP {resp.status_code}")
            data = resp.json()
            items_batch = data.get("items", [])
            current_head = data.get("current-item-index", cursor)

            for item_bucket in items_batch:
                for uuid_key, item in item_bucket.items():
                    item["uuid"] = uuid_key
                    item["server_index"] = cursor
                    all_items.append(item)
                cursor += 1

            if cursor >= current_head or not items_batch:
                break

        return all_items, current_head

    # ---------- 写入 ----------

    def commit(self, history_key: str, items: list[dict], ancestor_index: int) -> int:
        """
        向 history 提交一次 commit。
        items: [{uuid: "...", "e": "Task6", "t": 0, "p": {...}}, ...]
        返回新的 server-head-index。

        自动处理 Things Cloud 冲突 (HTTP 409)：
        - 手机/iPad 同时做了修改时，ancestor_index 过期
        - 后端返回新的 latest-server-index → 重新 commit
        - 最多重试 5 次，避免无限循环
        """
        extra = {
            "Schema": SCHEMA_HEADER,
            "Push-Priority": "10",          # Rust things3-cloud 用 10
            "App-Instance-Id": THINGS_APP_INSTANCE_ID,
            "App-Id": THINGS_APP_ID,
        }
        body = {it["uuid"]: {"e": it["e"], "t": it["t"], "p": it["p"]} for it in items}

        _log.info(f"[commit] ancestor={ancestor_index} items={len(items)} schema={SCHEMA_HEADER} appid={THINGS_APP_ID}")

        for attempt in range(5):
            resp = self._post(
                f"/version/1/history/{history_key}/commit",
                body=body,
                extra_headers=extra,
                params={"ancestor-index": ancestor_index, "_cnt": len(items)},
            )
            _log.info(f"[commit] attempt={attempt+1} HTTP={resp.status_code}")
            if resp.status_code == 200:
                new_head = resp.json().get("server-head-index", ancestor_index)
                _log.info(f"[commit] ✅ 成功 new_head={new_head}")
                return new_head
            if resp.status_code == 409:
                _log.info(f"[commit] ⚠️ 409 冲突 — 重试")
                try:
                    data = resp.json()
                    new_ancestor = data.get("latest-server-index")
                    _log.info(f"[commit]   server 建议 ancestor={new_ancestor}")
                    if new_ancestor and new_ancestor > ancestor_index:
                        ancestor_index = new_ancestor
                        continue
                except Exception:
                    pass
                head = self.get_history_head(history_key)
                ancestor_index = head.get("latest-server-index", ancestor_index + 1)
                _log.info(f"[commit]   从 head 获取 ancestor={ancestor_index}")
                continue
            _log.info(f"[commit] ❌ HTTP {resp.status_code}: {resp.text[:300]}")
            raise ThingsCloudError(
                f"Commit 失败: HTTP {resp.status_code} {resp.text[:300]}"
            )
        raise ThingsCloudError("Commit 重试 5 次后仍然冲突，请稍后再试")


# ============================================================
# Task 构建器 —— Task7 format (evanpurkhiser Rust SDK 生产代码使用)
# ============================================================

def build_task6_create_payload(
    title: str,
    notes: str | None = None,
    when: str | None = None,
    deadline: str | None = None,
    tags: list[str] | None = None,
    project_uuid: str | None = None,
    area_uuid: str | None = None,
) -> dict:
    """
    构建 Task7 格式的任务创建 payload (对齐 Rust SDK wire/task.rs TaskProps)。
    
    关键字段 (evanpurkhiser/things3-cloud):
      tt = title
      tp = task type (0=Todo, 1=Project, 2=Heading)
      ss = status (0=Incomplete, 2=Canceled, 3=Completed)
      st = schedule location (0=Inbox, 1=Anytime, 2=Someday)
      sr = scheduled date (秒级)
      tir = today index reference date (秒级)
      dd = deadline (秒级)
      tg = tag IDs
      pr = parent project IDs
      ar = area IDs
      ix = sort index
      lt = leaves tombstone
      tr = trashed
      icp = instance creation paused
      sb = evening bit (1=evening, 0=normal)
      xx = conflict_overrides (CRDT internal, 必带) ← Rust new.rs 强调!
      cd = creation date (秒级)
      md = modification date (秒级)
    """
    st, sr_ts = _resolve_when(when)
    now_ts = _things_now()  # 秒级

    # Rust base_new_props 里必带的 conflict_overrides
    conflict_overrides = {"_t": "oo", "sn": {}}

    payload = {
        "tt": title,
        "tp": 0,                 # Todo
        "ss": SS_PENDING,        # Incomplete
        "st": st,                # schedule: 0=Inbox, 1=Anytime, 2=Someday
        "tr": False,
        "icp": False,
        "lt": False,
        "ix": 0,
        "sb": 0,                 # normal (非 evening)
        "xx": conflict_overrides,  # ✅ CRDT internals — Rust SDK 必带!
        "cd": now_ts,
        "md": now_ts,
    }

    if notes:
        payload["nt"] = notes

    if sr_ts is not None:
        payload["sr"] = int(sr_ts)   # Rust 里是 Option<i64>

    # tir = today reference date (仅 Anytime/Today 需要)
    if st == ST_ANYTIME:
        payload["tir"] = int(sr_ts if sr_ts else _date_to_ts(datetime.now().strftime("%Y-%m-%d")))

    if deadline:
        try:
            payload["dd"] = float(_date_to_ts(deadline))  # Rust 是 f64
        except ValueError:
            pass

    if tags:
        payload["tg"] = list(tags)

    if project_uuid:
        payload["pr"] = [project_uuid]

    if area_uuid:
        payload["ar"] = [area_uuid]

    return payload


# 保留旧名作别名, 兼容 app.py 的调用
build_task6_payload = build_task6_create_payload


def build_task6_modify_payload(
    status: int | None = None,
    stop_date: float | None = None,
    md: float | None = None,
    trashed: bool | None = None,
    deadline: float | None = None,
) -> dict:
    """
    构建 Task7 modify payload (对齐 Rust SDK TaskPatch)。
    TaskPatch 所有字段都是 Option, 跳过 None 的 (Rust serde skip_serializing_if = "Option::is_none")。
    
    简化版: 只包含我们需要修改的字段。
    """
    p = {}
    if status is not None:
        p["ss"] = status
    if stop_date is not None:
        p["sp"] = stop_date
    if md is not None:
        p["md"] = md
    if trashed is not None:
        p["tr"] = trashed
    if deadline is not None:
        p["dd"] = deadline
    return p


# ============================================================
# 高层便捷接口
# ============================================================

class Things:
    """高层 Things Cloud 操作封装。"""

    def __init__(self, email: str, password: str, history_key: str | None = None):
        self.client = ThingsClient(email, password)
        if history_key:
            self.history_key = history_key
        else:
            # 自动获取
            info = self.client.verify()
            self.history_key = info["history-key"]
        self._head_index = None
        self._tasks = None

    # ---------- 写入 ----------

    def _compute_new_sort_index(self, st: int, project_uuid: str | None = None):
        """
        v2.5.12: 计算新任务的排序位 (ix), 对齐官方客户端行为。
        官方客户端把新任务插入目标列表**顶部**, 按 ix 升序展示 →
        取同列表现有最小 ix 再减一个步长, 保证排到最前面。
        之前固定写 ix=0, 手机端把所有 PC 任务视作同一位置 → 顺序"随机"。
        """
        try:
            self._maybe_refresh()
            # v2.5.15 修复: 缓存为 None 时必须强拉云端, 否则 same_list 为空 → ix 恒为 0
            if self._tasks is None:
                self.sync()
            tasks = self._tasks or []
            same_list = [t for t in tasks
                         if t.get("st_code") == st and not t.get("trashed")]
            if project_uuid:
                same_list = [t for t in same_list
                             if project_uuid in (t.get("project_uuid") or [])]
            ix_vals = [t.get("ix") for t in same_list if t.get("ix") is not None]
            if not ix_vals:
                return 0
            return min(ix_vals) - 100
        except Exception:
            return 0

    def add_task(
        self,
        title: str,
        notes: str | None = None,
        when: str | None = None,
        deadline: str | None = None,
        tags: list[str] | None = None,
        project_uuid: str | None = None,
    ) -> str:
        """
        添加一个新任务。when 可选值:
          'inbox'  | 'today' | 'evening' | 'anytime' | 'someday' | 'YYYY-MM-DD' | 'tomorrow'
        返回新任务的 UUID。
        """
        task_uuid = new_uuid()
        payload = build_task6_payload(
            title=title, notes=notes, when=when,
            deadline=deadline, tags=tags, project_uuid=project_uuid,
        )
        # v2.5.12: 按官方规则分配排序位 (新任务置顶)
        st_new, _sr_new = _resolve_when(when)
        payload["ix"] = self._compute_new_sort_index(st_new, project_uuid)

        # 获取最新 head index
        head = self.client.get_history_head(self.history_key)
        ancestor = head.get("latest-server-index", 0)

        items = [{
            "uuid": task_uuid,
            "e": KIND_TASK6,
            "t": ACTION_CREATED,
            "p": payload,
        }]
        self.client.commit(self.history_key, items, ancestor)
        # 重置缓存
        self._head_index = ancestor + 1
        self._tasks = None
        return task_uuid

    # ---------- 读取 ----------

    def _maybe_refresh(self):
        """
        检查云端有没有新 commit —— 有就增量拉取更新本地缓存。
        这是"iPhone 上完成的任务, PC 端看不到"的根因修复。
        """
        try:
            head_info = self.client.get_history_head(self.history_key)
            cloud_head = head_info.get("latest-server-index", 0)
            if self._head_index is None or cloud_head > self._head_index:
                # 有新数据 → 增量拉取
                raw_items, new_head = self.client.sync_history_items(
                    self.history_key, self._head_index or 0
                )
                # 如果是全量 (第一次), 直接重建; 否则增量 merge
                if self._head_index is None:
                    self._tasks = _rebuild_state(raw_items)
                else:
                    # 增量: 把新 items 合并到旧 state 里重建 (简单可靠)
                    # 把旧缓存转成原始 items 不方便, 直接全量重建
                    all_raw, _ = self.client.sync_history_items(self.history_key, 0)
                    self._tasks = _rebuild_state(all_raw)
                self._head_index = cloud_head
        except Exception as e:
            # 网络错误不影响使用 — 继续用旧缓存
            import logging
            logging.getLogger("things").debug(f"增量刷新失败 (离线?): {e}")

    def sync(self) -> list[dict]:
        """从云端拉取所有任务状态 (从 0 开始重建)。"""
        raw_items, head = self.client.sync_history_items(self.history_key, 0)
        self._head_index = head
        self._tasks = _rebuild_state(raw_items)
        return self._tasks

    def get_all_tasks(self) -> list[dict]:
        """获取所有任务 (包括已完成/已删除 —— 供前端全量展示)。"""
        self._maybe_refresh()
        if self._tasks is None:
            self.sync()
        return list(self._tasks)

    def get_tasks(self, list_name: str = "today", *, keyword: str | None = None) -> list[dict]:
        """
        按列表名获取任务:
          'all' | 'inbox' | 'today' | 'anytime' | 'someday' | 'upcoming' | 'trash'
        注: trash 列表自动不过滤 only_pending (所有被删除的都显示)
        """
        self._maybe_refresh()
        if self._tasks is None:
            self.sync()
        only_pending = list_name != "trash"
        return filter_tasks(self._tasks, only_pending=only_pending, list_name=list_name, keyword=keyword)

    def get_completed(self) -> list[dict]:
        """获取已完成任务。"""
        self._maybe_refresh()
        if self._tasks is None:
            self.sync()
        return [t for t in self._tasks if t["human_status"] == "completed"]

    def get_tags(self) -> list[dict]:
        """
        获取所有标签及其任务数量。
        返回 [{"tag": "xxx", "count": 5}, ...] 按数量倒序。
        注: 排除 trashed 的任务 (trash 里的标签不算)。
        """
        self._maybe_refresh()
        if self._tasks is None:
            self.sync()
        from collections import Counter
        counter: Counter = Counter()
        for t in self._tasks:
            if t.get("trashed"):
                continue
            for tag in (t.get("tags") or []):
                counter[tag] += 1
        return [{"tag": k, "count": v} for k, v in counter.most_common()]


# ============================================================
# 状态重建 (从 history items 构建当前任务列表)
# ============================================================

def _rebuild_state(items: list[dict]) -> list[dict]:
    """
    将 history items 重建为**完整**的当前任务状态快照。
    包括所有状态: 待办 / 已完成 / 已取消 / 已删除。

    重要: 第一遍先扫 Tag4 / Area3 实体检出 {uuid: 中文名} 映射,
          第二遍处理 Task*, 格式化时把 tg/pr/ar 的 UUID 翻译成中文。
    """
    # ---------- 第一遍: 扫 Tag4 / Area3, 构建名字映射 ----------
    tag_map: dict[str, str] = {}       # Tag4 uuid -> 标签中文名
    area_map: dict[str, str] = {}      # Area3 uuid -> 区域名

    # 用 state 累积 Tag4/Area3 的最新 payload (支持 modified 覆盖)
    meta_state: dict[str, tuple[str, dict]] = {}  # uuid -> (kind, latest_payload)

    for item in items:
        try:
            uuid = item["uuid"]
            kind = item.get("e", "")
            action = item.get("t", -1)
            payload = item.get("p", {})
            if not isinstance(payload, dict):
                payload = {}

            if kind == KIND_TAG or kind == KIND_AREA:
                if action == ACTION_CREATED or uuid not in meta_state:
                    meta_state[uuid] = (kind, dict(payload))
                elif action == ACTION_MODIFIED and uuid in meta_state:
                    prev_kind, prev_p = meta_state[uuid]
                    prev_p.update(payload)
                    meta_state[uuid] = (prev_kind, prev_p)
        except Exception:
            continue

    # 从 meta_state 提取名字
    for uuid, (kind, p) in meta_state.items():
        name = p.get("tt", "") if isinstance(p.get("tt"), str) else ""
        if not name:
            # Fractus 兜底: {"o":"text"} 或 {"o":{"c":"..."}}
            name = (p.get("tt") or p.get("pn") or "")
            if isinstance(name, dict):
                name = (name.get("o") or name.get("c") or "")
                if isinstance(name, dict):
                    name = name.get("c", "")
        if kind == KIND_TAG and name:
            tag_map[uuid] = name
        elif kind == KIND_AREA and name:
            area_map[uuid] = name

    _log.debug(f"[rebuild] tag_map={len(tag_map)} area_map={len(area_map)}")

    # ---------- 第二遍: 处理 Task* ----------
    state: dict[str, dict] = {}

    for item in items:
        try:
            uuid = item["uuid"]
            kind = item.get("e", "")
            action = item.get("t", -1)
            payload = item.get("p", {})

            # 只处理 Task* 系列 (任务/项目/Heading)
            if not (kind.startswith("Task") or kind in (KIND_TASK6, KIND_TASK7)):
                continue

            # payload 可能是非 dict (Fractus 旧格式), 兜底
            if not isinstance(payload, dict):
                payload = {}

            if action == ACTION_CREATED or uuid not in state:
                state[uuid] = {"uuid": uuid, "kind": kind, "p": dict(payload)}
            elif action == ACTION_MODIFIED:
                if uuid in state:
                    state[uuid]["p"].update(payload)
        except Exception as e:
            print(f"[rebuild] skip item: {e}")
            continue

    # 格式化输出 —— 单条坏数据不炸全量
    result = []
    for v in state.values():
        try:
            result.append(_format_task_full(v, tag_map=tag_map, area_map=area_map))
        except Exception as e:
            print(f"[rebuild] format fail {v.get('uuid','?')}: {e}")
    return result


def _format_task_full(raw: dict, *, tag_map: dict[str, str] | None = None,
                      area_map: dict[str, str] | None = None) -> dict:
    """
    把原始 task 格式化成前端友好的 dict。
    tag_map / area_map: 由 _rebuild_state 传入的 {uuid: 中文名} 映射。
    """
    tag_map = tag_map or {}
    area_map = area_map or {}
    p = raw.get("p", {})
    # 类型映射
    tp_map = {0: "task", 1: "project", 2: "heading"}

    # schedule 名字
    st_map = {
        ST_INBOX: "inbox",
        ST_ANYTIME: "anytime",
        ST_SOMEDAY: "someday",
    }

    # 时间戳 -> 可读日期 (Things Cloud sr/sp/dd 都是"秒"级, 兼容旧代码毫秒)
    def _ts_to_date(ts):
        if not ts:
            return ""
        try:
            # 自动识别秒/毫秒: > 1e12 是毫秒, 否则按秒
            if abs(float(ts)) > 1e12:
                t = float(ts) / 1000.0
            else:
                t = float(ts)
            return datetime.fromtimestamp(t).strftime("%Y-%m-%d")
        except Exception:
            return ""

    # 安全的字符串提取 —— Things Cloud 某些字段在 Fractus 协议下是 dict 或 list
    def _safe_str(v, default=""):
        if v is None:
            return default
        if isinstance(v, str):
            return v.strip()
        if isinstance(v, dict):
            # 可能是 Fractus 格式 {"o":"text"} 或 {"o":{"c":"..."}}
            if "o" in v and isinstance(v["o"], str):
                return v["o"].strip()
            if "c" in v and isinstance(v["c"], str):
                return v["c"].strip()
            # 兜底: 提取所有字符串值
            out_parts = []
            for val in v.values():
                if isinstance(val, str):
                    out_parts.append(val)
                elif isinstance(val, dict):
                    out_parts.append(_safe_str(val))
            return " ".join(p for p in out_parts if p).strip() or default
        if isinstance(v, list):
            return " ".join(
                _safe_str(i) for i in v if isinstance(i, (str, dict))
            ).strip() or default
        return str(v).strip()

    def _safe_int(v, default=0):
        try:
            if v is None: return default
            if isinstance(v, bool): return int(v)
            return int(v)
        except Exception:
            return default

    def _safe_bool(v, default=False):
        if v is None: return default
        if isinstance(v, bool): return v
        if isinstance(v, (int, float)): return bool(v)
        return default

    def _safe_list(v):
        if v is None: return []
        if isinstance(v, list):
            return [_safe_str(i) if isinstance(i, (str, dict)) else str(i) for i in v]
        if isinstance(v, dict):
            # Fractus 格式的 tag 字典, 尝试提取 key
            return [k for k in v.keys() if isinstance(k, str)]
        if isinstance(v, str):
            return [v]
        return []

    ss = _safe_int(p.get("ss"), SS_PENDING)
    tr = _safe_bool(p.get("tr"), False)
    tp = _safe_int(p.get("tp"), 0)
    st = _safe_int(p.get("st"), ST_INBOX)
    human_status = "pending" if ss in (SS_PENDING, 0) else (
        "completed" if ss == SS_COMPLETED else (
            "canceled" if ss == SS_CANCELED else "pending"
        )
    )
    if tr: human_status = "trashed"

    return {
        "uuid": raw["uuid"],
        "kind": raw["kind"],
        "title": _safe_str(p.get("tt") or p.get("ti"), "(no title)"),
        "notes": _safe_str(p.get("nt"), ""),
        "status": ss,
        "human_status": human_status,
        "trashed": tr,
        "type": tp_map.get(tp, "task"),
        "schedule": st_map.get(st, "inbox"),
        "st_code": st,
        "ix": p.get("ix"),          # v2.5.12: 列表内排序位 (官方客户端按此排序)
        "scheduled_ms": p.get("sr"),
        "scheduled_date": _ts_to_date(p.get("sr")),
        "deadline_ms": p.get("dd") or p.get("dl"),
        "deadline_date": _ts_to_date(p.get("dd") or p.get("dl")),
        "completion_date": _ts_to_date(p.get("sp") or p.get("comd")),
        # tags: Task6.tg 存的是 Tag4 UUID 列表 → 翻译成中文名
        "tags": [tag_map.get(u, u) for u in _safe_list(p.get("tg"))],
        "project_uuid": p.get("pr"),
        "area_uuid": p.get("ar"),
        "heading_uuid": p.get("hd"),
        "project_name": "",   # Project 是 tp=1 的 Task6, 需额外 project_map (留空, 后期补)
        "area_name": area_map.get(p.get("ar"), "") if p.get("ar") else "",
        "created_ms": p.get("cd"),
        "created_date": _ts_to_date(p.get("cd")),
    }


def parse_title_date(title: str):
    """
    v2.5.15: 解析任务标题开头的日期前缀, 用于"按日期排序"。
    支持格式:
      261113-xxx      → 2026-11-13  (YYMMDD + 分隔符)
      20261113-xxx    → 2026-11-13  (YYYYMMDD + 分隔符)
      2026-11-13 xxx  → 2026-11-13  (完整日期开头)
    没有前缀返回 None。
    """
    if not title:
        return None
    t = str(title).strip()
    m = re.match(r"^(\d{6}|\d{8})(?=[-\u2013\u2014\s.:、：,，_])", t)
    if m:
        d = m.group(1)
        try:
            if len(d) == 6:
                return datetime.strptime(f"20{d[:2]}{d[2:4]}{d[4:6]}", "%Y%m%d").date()
            return datetime.strptime(d, "%Y%m%d").date()
        except ValueError:
            return None
    m = re.match(r"^(20\d{2})[-/.](\d{1,2})[-/.](\d{1,2})(?=[-\s.:、：,，_)]|$)", t)
    if m:
        try:
            return datetime.strptime(
                f"{m.group(1)}-{int(m.group(2)):02d}-{int(m.group(3)):02d}", "%Y-%m-%d"
            ).date()
        except ValueError:
            return None
    return None


def filter_tasks(tasks: list[dict], *, only_pending: bool = True,
                 list_name: str | None = None, task_type: str | None = None,
                 keyword: str | None = None, tag_filter: str | None = None) -> list[dict]:
    """
    按 Things 的真实列表逻辑过滤:
      - inbox:    st=0 (无任何调度)
      - today:    st=1/2 且 sr ≤ 今天 (含过期任务)
      - anytime:  st=1 且 (sr 为空 或 sr > 今天)
      - someday:  st=2 且 sr > 今天
      - upcoming: 同 someday
      - trash:    trashed=True
      - all:      不过滤
      - tag_filter: 额外按标签名过滤 (大小写敏感, 精确匹配)
    """
    from datetime import datetime as _dt, timezone as _tz

    # 今天的本地日期 (不含时分秒)
    now_local = _dt.now()
    today_midnight = _dt(now_local.year, now_local.month, now_local.day)
    today_ts = int(today_midnight.timestamp())   # 秒级 (Things Cloud 用秒)
    today_date = now_local.date()                # v2.5.13: 日期对日期比较用

    def _is_today_or_overdue(sr_ms_or_s):
        """判断一个任务的 sr (秒或毫秒) 的日期是否 <= 今天
        v2.5.13: 按"日期对日期"比较 — 官方客户端把日期存为 UTC 零点 (北京时间早上8点),
        旧版 PC 存本地零点; 若用时间戳对比本地零点, 手机排的"今天"任务会被误判为未来。
        """
        if not sr_ms_or_s:
            return False
        try:
            v = float(sr_ms_or_s)
            if v > 1e12:
                v = v / 1000.0
            return _dt.fromtimestamp(v).date() <= today_date
        except Exception:
            return False

    def _is_scheduled_future(sr_ms_or_s):
        if not sr_ms_or_s:
            return False
        try:
            v = float(sr_ms_or_s)
            if v > 1e12:
                v = v / 1000.0
            return _dt.fromtimestamp(v).date() > today_date
        except Exception:
            return False

    result = []
    for t in tasks:
        # 🚨 所有非 trash 列表都要跳过 trashed=True 的任务 (iOS Things 也这么做)
        # 这是"trash 任务仍显示在 inbox 里"的根因
        if list_name != "trash" and t.get("trashed"):
            continue

        if only_pending and t["human_status"] not in ("pending",):
            continue
        if task_type and t["type"] != task_type:
            continue

        if list_name:
            st = t.get("st_code", 0)
            sr = t.get("scheduled_ms")

            if list_name == "all":
                pass
            elif list_name == "inbox":
                # Things Inbox = st=0
                if st != 0:
                    continue
            elif list_name == "today":
                # Things Today = st=1/2 AND sr ≤ 今天 (含过期)
                if not _is_today_or_overdue(sr):
                    continue
            elif list_name == "anytime":
                # Anytime = st=1 AND (sr 为空 OR sr > 今天)
                if st != 1:
                    continue
                if sr and _is_today_or_overdue(sr):
                    continue  # 已经进今天了
            elif list_name in ("someday", "upcoming"):
                # Someday = st=2 AND sr > 今天
                if st != 2:
                    continue
                if not _is_scheduled_future(sr):
                    continue
            elif list_name == "all_scheduled":
                pass
            elif list_name == "projects":
                # Projects: type=project 的待办任务
                if t.get("type") != "project":
                    continue
            elif list_name == "logbook":
                # Logbook = completed + canceled (不过滤 only_pending)
                if t["human_status"] not in ("completed", "canceled"):
                    continue
            elif list_name == "trash":
                # Trash = trashed=True (无论 st 是什么)
                if not t.get("trashed"):
                    continue
            elif list_name == "anytime":
                # Anytime 独立列表: st=1 且 (sr 为空 或 sr > 今天)
                if st != 1:
                    continue
                if sr and _is_today_or_overdue(sr):
                    continue
            else:
                if t["schedule"] != list_name:
                    continue

        if keyword:
            kw = keyword.lower().strip()
            if kw and kw not in t["title"].lower() and kw not in t["notes"].lower():
                continue

        if tag_filter:
            tags = t.get("tags") or []
            if tag_filter not in tags:
                continue

        result.append(t)

    # 排序: 最新日期在最上面
    # (1) 有 scheduled_ms 的按 scheduled_ms 倒序
    # (2) 无 scheduled_ms 的按 created_ms 倒序 (排在有日期的后面)
    # (3) 同层级按 uuid (FIFO 稳定)
    result.sort(key=lambda t: (
        t.get("scheduled_ms") if t.get("scheduled_ms") is not None else 0,
        t.get("created_ms") or 0,
    ), reverse=True)
    return result


# ============================================================
# 去重逻辑
# ============================================================

def find_duplicates(tasks: list[dict]) -> dict:
    """
    在任务列表里找出所有疑似重复项。
    返回 {"exact": [...], "similar": [...]}
    其中每个分组是 [{uuid, title, ...}, ...]
    """
    # 只对待办任务去重
    pending = [t for t in tasks if t["human_status"] == "pending"]

    # 1. 完全相同（标题完全一致）
    title_map: dict[str, list[dict]] = {}
    for t in pending:
        key = t["title"].strip().lower()
        if len(key) > 0:
            title_map.setdefault(key, []).append(t)

    exact_groups = [v for v in title_map.values() if len(v) >= 2]

    # 2. 相似标题（去标点/首尾空格后、或关键词高度重叠）
    def _normalize(s: str) -> str:
        import re
        s = s.lower().strip()
        s = re.sub(r"[，。！？、,.!?·\-—_\s]+", "", s)
        return s

    norm_map: dict[str, list[dict]] = {}
    for t in pending:
        key = _normalize(t["title"])
        if len(key) > 2:
            norm_map.setdefault(key, []).append(t)

    norm_groups = [v for v in norm_map.values() if len(v) >= 2]

    # 合并: 完全相同 + 标准化后相同（可能互相重叠，用 exact 优先）
    seen_uuids: set[str] = set()
    merged_exact = []
    for g in exact_groups:
        uuids = {t["uuid"] for t in g}
        if not uuids & seen_uuids:
            merged_exact.append(g)
            seen_uuids |= uuids

    similar_groups = []
    for g in norm_groups:
        uuids = {t["uuid"] for t in g}
        if not uuids & seen_uuids:
            similar_groups.append(g)
            seen_uuids |= uuids

    return {"exact": merged_exact, "similar": similar_groups}


def build_dedupe_plan(tasks: list[dict]) -> dict:
    """
    生成去重方案 —— 每组选一个保留（最早创建的，假设最早的是原始）。
    返回:
      {
        "groups": [
          {
            "type": "exact" | "similar",
            "keep_uuid": "...",
            "keep_title": "...",
            "remove_uuids": [...],
            "members": [{uuid, title, created_date}, ...]
          },
          ...
        ],
        "total_duplicates": 5,
        "groups_count": 3,
      }
    """
    dups = find_duplicates(tasks)
    plan = {"groups": [], "total_duplicates": 0}

    for gtype, groups in [("exact", dups["exact"]), ("similar", dups["similar"])]:
        for group in groups:
            # 按创建时间升序（最早的优先保留）
            sorted_g = sorted(
                group,
                key=lambda t: t.get("created_ms") or 0,
            )
            keep = sorted_g[0]
            remove = sorted_g[1:]
            plan["groups"].append({
                "type": gtype,
                "keep_uuid": keep["uuid"],
                "keep_title": keep["title"],
                "remove_uuids": [t["uuid"] for t in remove],
                "remove_titles": [t["title"] for t in remove],
                "members": [
                    {
                        "uuid": t["uuid"],
                        "title": t["title"],
                        "created_date": t.get("created_date", ""),
                        "schedule": t.get("schedule", ""),
                    }
                    for t in sorted_g
                ],
            })
            plan["total_duplicates"] += len(remove)

    plan["groups_count"] = len(plan["groups"])
    return plan
