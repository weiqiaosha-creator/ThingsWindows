# Things Windows
## v2.5.14 — 2026-11-10

### 📱 界面显示手机端对应版本号

- 登录页与主界面侧边栏新增版本行: `PC v2.5.14 · 兼容手机端 Things 3.22.8 (iOS)`
- 版本号由伪装编码自动推导 (32208 → 3.22.8), 与 `things_cloud.py` 的协议伪装常量单一来源, 不会出现两处不一致
- `/api/health` 新增 `phone_things_version` / `phone_things_platform` 字段

---

## v2.5.13 — 2026-11-09

### 🕐 时区口径修复 — 手机"今天"任务不再漏进 PC

- **现象**: 手机"今天"168 条, PC 只显示 158/161 条, 缺的恰好都是手机当天新建的任务
- **根因**: 官方客户端把日期存为 UTC 零点 (北京时间 08:00), PC 旧版按本地零点比较,
  手机排的"今天"任务被 PC 误判成"未来"而塞进"随时"
- **修复**: `filter_tasks` 的今天/随时/将来判断改为日期对日期 (两种写法都兼容);
  PC 创建任务的时间戳同步改为官方的 UTC 零点口径

---

## v2.5.12 — 2026-11-09

### 🔃 同步排序修复 + 置顶持久化

- **修复 PC 任务在手机端排序"随机"**: Task6 的 `ix` (列表内排序位) 此前固定写 0,
  官方手机客户端将所有 PC 任务视为同一位置。现在新建/移动任务时自动取目标列表
  最小 `ix` 再减一步长, 与官方客户端一样"新任务置顶"
- **修复置顶任务重启后消失**: 置顶列表原先存 WebView2 localStorage (会被清空),
  改为存 `%APPDATA%\ThingsWindows\pins.json` 磁盘文件, 重启/升级均不丢;
  老版本 localStorage 中已有的置顶会在首次启动时自动迁移
- 新增后端接口 `GET/POST /api/pins`

---

## v2.5.11 — 2026-11-03

### 🔐 开源保护版 — 授权密钥移出公开源码 + PyArmor 混淆

为配合 GitHub 开源发布, 本版本将授权体系升级为真正的保护版本:

- 签名密钥从 `lic.py` 移入独立的 `lic_secret.py`, 该文件加入 `.gitignore`
  **永不进入公开仓库** — 公开源码不再包含可生成任意授权码的密钥
- 全部核心模块 (app/main_window/auth_store/lic/lic_secret/things_cloud)
  经 PyArmor 混淆后打包, EXE 内密钥不再可直接提取
- **旧版本授权码在新版本中全部失效** (签名密钥已更换), 需使用新密钥重新签发
- 公共仓库仅发布本版本及之后的保护版本; 历史版本 (无保护/旧密钥易破解)
  全部移入私有仓库 ThingsWindows-Private

---

## v2.5.10 — 2026-10-13

### 🔒 版本护栏 — 手机端"需要更新"提示永久免疫

手机端受 iOS 16.2 限制, 最高只能运行 Things 3.22.8 且无法再升级。
手机端"其他端版本更高, 需要更新"弹窗由云端记录的客户端版本/schema 信息触发,
Windows 端是唯一可控的上报方 —— v2.5.10 把这一点做成结构性保证:

- 新增永久基准常量 `PHONE_VERSION_CEILING = "32208"` / `PHONE_SCHEMA_CEILING = "301"`
  (即手机端 Things 3.22.8 / iOS 16.2)
- 新增 `_enforce_version_guard()`: import 时自动钳制, 任何超过基准的版本/schema
  配置都会被压回并写警告日志; 非法值同样重置为基准
- 后续 Windows 任何功能迭代都不会向云端上报高于手机端的版本信息,
  从源头杜绝手机端更新弹窗
- 将来手机端若真升级, 只需同步上调这两个基准常量

---

## v2.4.4 — 2026-10-06

### 🐛 Vue/Tailwind 本地化 + 静态文件路由修复 + 🔑 永久授权

#### 1️⃣ Vue / Tailwind 本地化 (两层修复)

**第一层 (CDN → 本地文件)**
将 `vue.global.prod.js` (168KB) 和 `tailwindcss.js` (407KB) 下载到项目目录,
`index.html` 不再依赖 `unpkg.com` / `cdn.tailwindcss.com`, EXE 完全离线运行。

**第二层 (修复 PyInstaller --add-data 与 /static/ 路由的路径不匹配, 关键修复)**

PyInstaller `--add-data "vue.global.prod.js;."` 把文件解压到 `sys._MEIPASS/vue.global.prod.js` (根目录),
但 app.py 的 `/static/` 路由用 `path.lstrip("/")` 拼路径:
- 浏览器请求 `/static/vue.global.prod.js`
- 旧代码: `os.path.join(STATIC_DIR, path.lstrip("/"))` → `sys._MEIPASS/static/vue.global.prod.js`
- 多了一层 `static/` 目录 → 404 → Vue/Tailwind 全部加载失败 → `{{ }}` 原样显示

修复 app.py L149: 用 `path[len("/static/"):]` 直接取文件名, 跳过 static/ 前缀,
`os.path.join(STATIC_DIR, fname)` 正确找到 `sys._MEIPASS/vue.global.prod.js`。

验证: 打包后 curl `/`, `/static/vue.global.prod.js`, `/static/tailwindcss.js` 全部 200 OK。

#### 2️⃣ 本机永久授权激活

用户机器码 `9b21553aa0c7ac23`, 已生成 2100-01-01 到期的永久授权码并写入本地 `license.dat`。

---

## v2.4.3 — 2026-10-06

### 🐛 收件箱同步根因修复 + 🏷️ 按标签归类

#### 1️⃣ 收件箱同步根因修复 (filter_tasks trashed 泄漏)

**根因**: `filter_tasks()` 的 inbox/today/anytime/someday 等所有非 trash 列表分支,
**都没有排除 trashed=True 的任务**。iOS Things 客户端会自动隐藏 trashed 任务,
我们的 PC 端漏掉了这个逻辑 → 被移到垃圾桶的任务仍然显示在收件箱里, 造成 "PC 10 vs iPhone 9"。

修复: 在 `filter_tasks()` 循环最前面加统一跳过:
```python
if list_name != "trash" and t.get("trashed"):
    continue
```

**验证**:
```
修复前: inbox(pending)=10  其中 1 条 trashed=True 混在里面 ❌
修复后: inbox(pending)=10  trashed 泄漏=0 ✅
        trash 列表=2 (正确显示) ✅
```

这个 bug 影响所有列表 — today/anytime/someday/all/日志簿 里都不应该出现 trashed 任务。
一行修复全部解决。

#### 2️⃣ 按标签归类

新增标签归类功能, 方便按项目/标签批量查看任务。

后端:
| 文件 | 说明 |
|---|---|
| `things_cloud.py` get_tags() | 返回所有标签及任务数 (Counter) |
| `things_cloud.py` filter_tasks | 新增 `tag_filter` 参数 |
| `app.py` /api/tags | GET 返回标签列表 |
| `app.py` /api/tasks?tag=xxx | 按标签过滤任务 |

前端:
- 侧边栏 "🏷️ 按标签" 可展开/收起
- 展开显示所有标签 + 每个标签的任务数
- 点标签 → 显示该标签下所有任务 (待办+已完成)

#### 修复文件

| 文件 | 改动 |
|---|---|
| `things_cloud.py` | filter_tasks 加 trashed 统一跳过; 加 tag_filter 参数; 加 get_tags() |
| `app.py` | 新增 /api/tags; /api/tasks 加 tag 参数支持 |
| `index.html` | 侧边栏标签入口+子菜单; fetchTasks 支持 tag: 前缀; currentTitle 支持 tag 标题 |

#### 📦 交付物

| 文件 | 说明 |
|---|---|
| `dist/ThingsWindows.exe` | **v2.4.3 最新版** |
| `dist/ThingsWindows_v2.4.3.exe` | 带版本号命名 |

---

 — 更新日志

所有版本号遵循 [语义化版本](https://semver.org/) (SemVer)。
旧版本完整归档在 `releases/<版本>/` 下，可随时回退。

## v2.4.2 — 2026-10-06

### 🗑️ 垃圾桶 + 📛 版本号全链路修复 + 🔄 收件箱同步

#### 1️⃣ 新增垃圾桶侧边栏

之前侧边栏没有垃圾桶入口, 用户移到垃圾桶的任务无法在 PC 端查看/恢复。
现在侧边栏最底部新增 🗑️ 垃圾桶入口, 可以查看所有被删除的任务。

改动:
| 文件 | 说明 |
|---|---|
| `things_cloud.py` filter_tasks | 新增 `trash` list_name (过滤 trashed=True 的任务) |
| `things_cloud.py` get_tasks | trash 列表自动跳过 only_pending (显示所有被删除的) |
| `app.py` /api/stats | 新增 `trash` 计数 |
| `index.html` sidebar | 垃圾桶 🗑️ 入口 + 标题/副标题 |

#### 2️⃣ 版本号全链路修复

之前版本号散落在三处, 全部硬编码 v2.0:
- `main_window.py:116` `title="Things Windows v2.0"` → 导致窗口标题显示 v2.0
- `main_window.py:88` console print 硬编码 v2.0
- 登录页没有版本号显示

修复:
- `main_window.py` 动态 `import app; DISPLAY_VERSION` 拿到版本号
- 窗口标题 `f"Things Windows v{webapp.DISPLAY_VERSION}"` → **v2.4**
- 登录页底部加 `v{{ version }}` (从后端 /api/health 动态拉取) → **v2.4**
- 侧边栏版本徽标保持不变 (上一版已加)

#### 3️⃣ 收件箱同步确认

实测收件箱计数:
```
iPhone 收件箱: 9 (用户移了1条到垃圾桶)
PC filter_tasks(inbox, pending=True): 9 ✅
```

后端 `_maybe_refresh()` + 前端 15 秒轮询的闭环已在 v2.2.0 修好。
用户之前看到的 "PC 10 vs iPhone 9" 是旧 EXE (v2.3.x) 版本缓存未刷新的问题, v2.4.x 已彻底修复。

#### 修复文件

| 文件 | 改动 |
|---|---|
| `main_window.py` | 版本号从 app.DISPLAY_VERSION 动态取, 删除硬编码 v2.0 |
| `things_cloud.py` | filter_tasks 新增 trash 分支; get_tasks trash 跳过 only_pending |
| `app.py` | stats 新增 trash 计数 |
| `index.html` | 侧边栏垃圾桶 + 登录页底部版本号 |

#### 📦 交付物

| 文件 | 说明 |
|---|---|
| `dist/ThingsWindows.exe` | **v2.4.2 最新版** |
| `dist/ThingsWindows_v2.4.2.exe` | 带版本号命名 |
| `releases/license-tools/` | 授权码工具独立归档 |

---

## v2.4.0 — 2026-10-06

### 🔐 授权码体系 + 🕐 任务显示创建/效期时间

#### 1️⃣ 授权码体系 (机器码绑定 + HMAC-SHA256 + 有效期)

设计目标: 把 exe 分享给他人时, 可以按实际需要授权 (7天/30天/90天/永久),
**授权码只能在指定电脑上用** (机器码绑定), 拷到别的电脑自动失效。

| 组件 | 文件 | 说明 |
|---|---|---|
| 验证模块 | `lic.py` | 内嵌到 EXE 的授权验证逻辑 |
| 生成工具 | `lic.py gen` | 授权方命令行生成授权码 |
| 存储位置 | `%APPDATA%/ThingsWindows/license.dat` | 本机激活记录 |

授权码格式 (Base64URL):
```
┌──────┬──────────────┬──────────┬─────────────────────┐
│ 版本 │ 机器码 (8字节) │ 过期时间  │ HMAC-SHA256 签名     │
└──────┴──────────────┴──────────┴─────────────────────┘
```

**三层验证**:
1. HMAC 签名校验 — 防篡改
2. 机器码匹配 — 防串用 (换电脑自动失效)
3. 过期时间检查 — 防超时

有效期选项: 7 天 / 30 天 / 90 天 / 指定日期 / 永久

**使用流程**:
```
使用者 (拿到 EXE)                    授权方 (你)
───────────────                    ──────────
① 打开 ThingsWindows
② 点侧边栏底部 🔑 授权状态
③ 复制机器码 (16 字符 hex) ─────→ ④ lic.py gen 9b21553aa0c7ac23 --days 30
   例: 9b21553aa0c7ac23           ⑤ 得到授权码 ──────→ ⑥ 发给使用者
                                   ⑦ 粘贴激活 → ✅ 通过
```

**生成命令**:
```bash
python lic.py machine                           # 显示本机机器码
python lic.py gen <机器码> --days 30            # 30 天
python lic.py gen <机器码> --days 0             # 永久
python lic.py gen <机器码> --expiry 2026-12-31  # 指定到期日
python lic.py verify <授权码>                   # 验证一个授权码
python lic.py status                            # 检查本地已激活的授权
```

新增 API 端点:
| 端点 | 方法 | 说明 |
|---|---|---|
| `/api/license` | GET | 返回当前授权状态 |
| `/api/machine-code` | GET | 返回本机机器码 |
| `/api/license/activate` | POST | 激活授权码 |
| `/api/license/revoke` | POST | 清除本机授权 |

#### 2️⃣ 任务列表显示时间信息

每条任务现在显示:
```
🆕 创建日期   📅 效期/安排   ⏰ 截止日期   ✅ 完成日期(已完成时)
```

详情面板也增加了独立的 **效期**、**截止**、**完成** 时间行 (带颜色区分)。

修改文件:
| 文件 | 改动 |
|---|---|
| `lic.py` 🆕 | 授权码验证 + 生成 (内嵌 SECRET + HMAC) |
| `app.py` | 新增 4 个授权码 API 端点 |
| `index.html` | 侧边栏授权状态条 + 激活模态框 + 任务行时间 + 详情面板时间 |

#### 📦 交付物

| 文件 | 说明 |
|---|---|
| `dist/ThingsWindows.exe` | **v2.4.0 最新版** |
| `dist/ThingsWindows_v2.4.0.exe` | 带版本号命名 |
| `lic.py` | 授权码生成/验证工具 (授权方使用) |
| `releases/v2.4.0/` | 完整归档 |

---

---

## v2.3.1 — 2026-10-06

### 🐛 紧急修复：DPAPI 参数错误导致记住密码完全不可用

**v2.3.0 里引入的 `auth_store.py`（记住密码 + 设备指纹 + 二次验证）因为 pywin32 API 参数签名理解错误，导致 `CryptProtectData` / `CryptUnprotectData` 实际无法调用 —— 整个安全体系是摆设。**

#### 根因：pywin32 参数位置错位

pywin32 的 `CryptProtectData` / `CryptUnprotectData` 签名和我以为的不一样：

```
CryptProtectData(data, desc, entropy, reserved, promptstruct, flags)   ← 6 个参数
CryptUnprotectData(data, entropy, reserved, promptstruct, flags)       ← 5 个参数
```

v2.3.0 写成了：

```python
CryptProtectData(plaintext, None, None, None, 0)     # ❌ 5 个: 把 flags=0 塞到了 promptstruct 位置
CryptUnprotectData(ciphertext, None, None, 0)         # ❌ 4 个: 同上
```

实际运行时报错：`TypeError: CRYPTPROTECT_PROMPTSTRUCT must be None or a tuple (got int)`

#### v2.3.1 修复

| 函数 | 修复前 | 修复后 |
|---|---|---|
| `CryptProtectData` | `(data, None, None, None, 0)` | **`(data, None, None, None, None, 0)`** |
| `CryptUnprotectData` | `(data, None, None, 0)` | **`(data, None, None, None, 0)`** |

#### 测试验证

```
DPAPI 加密解密: ✅ True
保存后 has_remembered: ✅ {'has': True, 'email': 'test@x.com', '2fa': True}
load_credentials 密码正确: ✅ True
2FA 验证正确密码: ✅ True
2FA 验证错误密码: ✅ False
删除成功: ✅
```

#### 📦 交付物

| 文件 | 说明 |
|---|---|
| `dist/ThingsWindows.exe` | **v2.3.1 最新版** |
| `dist/ThingsWindows_v2.3.1.exe` | 带版本号命名 |

---

## v2.3.0 — 2026-10-05

### 🔐 新增安全功能：记住密码 + 设备绑定 + 二次验证

**三层防护，解决"把 exe 拷到别的电脑就自动登录"的安全风险：**

| 层级 | 机制 | 效果 |
|---|---|---|
| **L1** DPAPI (Windows Data Protection API) | 用当前 Windows 用户 + 机器私钥加密密码 | 换 Windows 用户或换电脑 → 密码解不开 |
| **L2** 设备指纹 (MachineGuid) | 注册表 `HKLM\...\Cryptography\MachineGuid` 每台机器唯一 | 拷到别的电脑 → 指纹不匹配 → 直接拒绝读取 |
| **L3** 二次验证 PIN (可选) | PBKDF2-HMAC-SHA256 10 万次迭代哈希 | 同电脑同用户打开 EXE → 还要再输一次你自定义的 PIN |

**和 IP 地址无关** —— 同一台电脑换 WiFi/换热点都能记住；换到任何别的电脑（哪怕同 IP）都会失效。

#### 新增/修改文件

| 文件 | 说明 |
|---|---|
| `auth_store.py` 🆕 | 安全凭证存储模块（DPAPI + 设备指纹 + 2FA） |
| `app.py` | 新增 3 个接口 `/api/remembered` / `/api/auth-2fa` / `/api/remove-remembered` |
| `index.html` | 登录界面双流程：有记住的凭证 → 2FA/PIN 登录；无 → 手动登录 |

#### 存储位置

```
%APPDATA%\ThingsWindows\credentials.dat
```

内容为 JSON，密码字段是 DPAPI 加密后的 base64 blob（**没有任何明文密码**）。

#### API 新增端点

| 端点 | 方法 | 说明 |
|---|---|---|
| `/api/remembered` | GET | 启动时检查本机是否有记住的账号（返回 email + 是否需要 2FA，**不返回密码**） |
| `/api/auth-2fa` | POST | 用记住的凭证 + PIN 登录 |
| `/api/remove-remembered` | POST | 删除本机存储的凭证（"忘记密码"） |

---

## v2.2.0 — 2026-10-05

### 🔄 iPhone 同步自动轮询 + 旧版本 history 残留清理

**用户反馈：在 iPhone 上完成一个任务，PC 端要等很久甚至手动刷新才看到。根因是后端 `get_tasks()` 只在首次登录时 sync 一次，之后全靠内存缓存。**

#### 修复 1：后端 `_maybe_refresh()` 读操作前自动检查云端 head_index

```python
def _maybe_refresh(self):
    head = self.client.get_history_head(self.history_key)
    if head["latest-server-index"] != self._head_index:
        self.sync()   # 云端有新内容 → 重新 sync
```

**所有 `get_tasks()` / `get_completed()` / `get_all_tasks()` 调用前都会先跑一次这个检查。**

#### 修复 2：前端 15 秒定时轮询

```javascript
setInterval(async () => {
    if (auth.value) {
        await fetchTasks();
        await fetchStats();
    }
}, 15000);   // 15 秒
```

登录后自动开启，退出登录自动清理。**iPhone 上改任务 → 最多 15 秒 PC 端自动看到。**

---

## v2.1.1 — 2026-10-04

### 🔄 回退到 Things 3.21.x 兼容格式（iPhone Things 3.21.8 的"必须更新"根因）

**v2.1.0 用了 Rust SDK 的 Task7 + Schema 301 — 但那是给 Mac Things 3.22.9 用的，iPhone 3.21.8 只理解 Task6 + Schema 201。**

#### 核心发现

| 客户端版本 | EntityType | Schema Header | 我们之前是否用了 |
|---|---|---|---|
| **iPhone 3.21.8** | **Task6** | **201** | ❌ 我们发了 Task7 + 301 → 弹更新 |
| Mac Things 3.22.9 | Task7 | 301 | Rust SDK 用于 Mac 自己 |

**Things Cloud 把 EntityType + Schema 版本写入 history items。当 iPhone 3.21.8 拉取时发现 Task7 + Schema 301，认为有"更新版本的客户端"写入 → 强制弹"必须更新"。**

#### v2.1.1 修正

| 项目 | v2.1.0 (错误) | v2.1.1 (iPhone 兼容) |
|---|---|---|
| EntityType (e) | `"Task7"` | **`"Task6"`** |
| Schema Header | `"301"` | **`"201"`** |
| 伪装身份 | ThingsMac 3.22.9 | **ThingsMac 3.22.9（保留，更中性）** |
| 伪装 App-Id | ThingsMac | **ThingsMac（保留）** |
| Payload 字段 | 完整 TaskProps + `xx` | **完整 Task6 字段 + `xx` conflict_overrides** |
| 时间戳单位 | 秒级 f64 | 秒级 f64（保留，两者一致） |

#### 保留的正确修正（不再回退）

- ✅ payload 字段：`tt`（标题）、`dd`（截止日期）、`sr`、`tir`、`xx`（conflict_overrides）、`cd`、`md`
- ✅ 修改操作 payload 带 `md` + `sp`（标记完成时）
- ✅ 秒级时间戳（之前的毫秒是错的）
- ✅ Schema/App-Id/UA 统一加到 `_headers()` 所有请求
- ✅ Push-Priority: 10

#### 📦 交付物

| 文件 | 说明 |
|---|---|
| `dist/ThingsWindows.exe` | **v2.1.1 最新版** |
| `dist/ThingsWindows_v2.1.1.exe` | 带版本号命名 |
| `releases/v2.1.1/` | 归档 |

---

## v2.1.0 — 2026-10-04

### 🎯 最终协议完全对齐 evanpurkhiser Rust SDK（两个根因同时解决）

**v2.0.2 没解决，因为还漏了两个关键差异：EntityType 和 伪装身份。**

#### 差异 1：EntityType — Task6 → Task7（Rust 生产代码全用 Task7）

| 来源 | 创建任务 e 字段 | 修改任务 e 字段 |
|---|---|---|
| **evanpurkhiser Rust SDK** | `EntityType::Task7` (new.rs L389) | `EntityType::Task7` (mark.rs L223) |
| arthursoares Go SDK | 也是更新 Task7 | 也是 |
| 我们（之前） | `"Task6"` ❌ | `"Task6"` ❌ |

Task6 是 legacy format，Rust SDK 已在生产代码全面切换到 Task7。

#### 差异 2：伪装身份 — ThingsiPhone → ThingsMac

| 项目 | Rust SDK | Go SDK | 我们（之前）|
|---|---|---|---|
| UA | `ThingsMac/32209501` | `ThingsMac/32209501` | `ThingsiPhone/32108501` ❌ |
| App-Id | `com.culturedcode.ThingsMac` | `com.culturedcode.ThingsMac` | `com.culturedcode.ThingsiPhone` ❌ |
| CLIENT_INFO.nv | `"32209501"` | `"32209501"` | `"32108501"` ❌ |
| CLIENT_INFO.nn | `ThingsMac` | `ThingsMac` | `ThingsiPhone` ❌ |
| CLIENT_INFO.on | `macOS` | `macOS` | `iOS` ❌ |

**两个成功的 Things 3.x 兼容 SDK 都伪装成 Mac！** Things Cloud 对 iOS 客户端有更严格的版本检查，而对 ThingsMac 更宽容。

#### 差异 3：TaskProps 缺字段 — 加 `xx` (conflict_overrides)

Rust new.rs `base_new_props()` 必带 `conflict_overrides: Some(json!({"_t": "oo", "sn": {}}))` — 这是 CRDT 内部字段，缺少可能导致 Things Cloud 拒绝写入。

#### 完整协议清单（对齐 Rust SDK）

| 项目 | 值 |
|---|---|
| Schema | `"301"` (所有请求) |
| UA | `ThingsMac/32209501` |
| App-Id | `com.culturedcode.ThingsMac` |
| App-Instance-Id | `000...000-ThingsMac-000...000` |
| CLIENT_INFO.nv | `"32209501"` (8位版本号) |
| CLIENT_INFO.nn | `ThingsMac` |
| CLIENT_INFO.on | `macOS` |
| Push-Priority | `"10"` (commit) |
| EntityType (e) | **`"Task7"`** |
| 创建 payload | TaskProps 完整字段（含 `xx`、`sb`、`ix`、`lt`、`icp`） |
| 修改 payload | TaskPatch Option 风格（跳过 None） |
| 时间戳单位 | **秒级 float** (`f64`) |

#### 📦 交付物

| 文件 | 说明 |
|---|---|
| `dist/ThingsWindows.exe` | **v2.1.0 最新版**（100% 对齐 Rust SDK） |
| `dist/ThingsWindows_v2.1.0.exe` | 带版本号命名 |
| `releases/v2.1.0/` | 归档（EXE + 源码） |

#### ⚠️ iPhone Things 3.21.8 不升级也能用

本次改动故意伪装成 Mac Things 3.22.9，Schema 301，EntityType Task7 — 这些**对 iOS Things 3.x 完全向下兼容**。iPhone 不应该再弹更新。

---

## v2.0.2 — 2026-10-04

### 💥 致命修正：Schema Header 201 → 301（两个权威 SDK 验证）

**v2.0.1 的修正没生效，因为根因是 Schema header 本身。**

#### 根因：我们一直用错了 Schema 值！

| 来源 | Schema Header | 证据 |
|---|---|---|
| **evanpurkhiser Rust things3-cloud** | `"301"` | client.rs:23 `const SCHEMA: &str = "301"` |
| **arthursoares Go things-cloud-sdk** | `"301"` | histories.go:266 `req.Header.Add("Schema", "301")` |
| **我们之前（错误）** | `"201"` | 凭空猜的，没有源码依据 |

Schema "201" 可能是 Things 2.x 的遗留格式，Things Cloud 收到后无法正确识别为 Things 3.x 客户端 → **触发 iPhone 弹"您在另一台设备上使用了新版本"**。

#### 同步修正

| 项目 | v2.0.1 | v2.0.2 |
|---|---|---|
| Schema | `"201"` ❌ | **`"301"`** ✅ |
| Push-Priority | `"5"` | **`"10"`** (Rust SDK) |
| Schema 作用范围 | 仅 commit | **所有请求统一加** ✅ |
| App-Id | ThingsiPhone | **统一加到 `_headers()`** ✅ |
| App-Instance-Id | 仅 commit | **统一加到 `_headers()`** ✅ |

#### 📦 交付物

| 文件 | 说明 |
|---|---|
| `dist/ThingsWindows.exe` | **v2.0.2 最新版** |
| `dist/ThingsWindows_v2.0.2.exe` | 带版本号命名 |
| `releases/v2.0.2/` | 归档 |

---

## v2.0.1 — 2026-10-04

### 🔥 紧急修正：iOS 弹更新 + 同步失败（两个根因同时修）

#### 根因 1：CLIENT_INFO.nv 版本号格式错误 → iOS 弹"必须更新"

Things Cloud 版本号编码规则（来自 Go SDK）：**8 位数字 = 主1 + 次2 + 修2 + build3**

| 项目 | 旧值（错误） | 新值（正确） | Go SDK 示例 |
|---|---|---|---|
| `nv` (AppVersion) | `"32108"`（5位） | **`"32108501"`**（8位） | Mac `"32209501"` |
| `User-Agent` | `ThingsiPhone/32108` | **`ThingsiPhone/32108501`** | Go SDK `ThingsMac/32209501` |
| `ov` (OSVersion) | `"16.0"` | **`"16.5.1"`** | Go SDK `"15.7.3"`（完整3段） |

iOS Things 3.x 收到"未知版本号格式"的客户端 commit 时强制弹更新 → **已修复**。

#### 根因 2：完成任务 commit payload 缺字段 → iPhone 不同步

完成任务时我们只 commit 了 `{"ss": 3}`，Things Cloud 要求 Task6 modify 必须带：
- `md`（modification date 修改日期，秒级）—— **所有 modify 都需要**
- `sp`（completion date 完成日期，秒级）—— **仅 completed 时需要**

| 操作 | 旧 payload | 新 payload |
|---|---|---|
| 完成任务 | `{"ss": 3}` | **`{"ss": 3, "md": 1791119353.7, "sp": 1791119353.7}`** |
| 取消任务 | `{"ss": 2}` | **`{"ss": 2, "md": 1791119353.7}`** |
| 恢复任务 | `{"ss": 0}` | **`{"ss": 0, "md": 1791119353.7}`** |
| 扔垃圾桶 | `{"tr": true}` | **`{"tr": true, "md": 1791119353.7}`** |

#### 📦 交付物

| 文件 | 说明 |
|---|---|
| `dist/ThingsWindows.exe` | **v2.0.1 最新版**（原生窗口 + 协议完整修正） |
| `dist/ThingsWindows_v2.0.1.exe` | 带版本号命名 |
| `releases/v2.0.1/` | 归档（EXE + 源码） |

---

## v2.0.0 — 2026-10-04

### 🎉 里程碑：原生桌面窗口 + 协议完全对齐 iOS 3.21.8

**重大升级，从"浏览器后端"演进为"原生桌面应用"。**

#### ✅ 修正 Things Cloud API 协议字段（对齐 Go SDK）

参考 [arthursoares/things-cloud-sdk](https://github.com/arthursoares/things-cloud-sdk) 的权威定义，修正了 3 个关键字段：

| 字段 | 旧值（错误） | 新值（正确） | Go SDK 类型 | 说明 |
|---|---|---|---|---|
| **标题** | `ti` | **`tt`** | `Title *string` | `ti` 是 TaskIndex（排序位置），`tt` 才是标题 |
| **截止日期** | `dl` | **`dd`** | `DeadlineDate *Timestamp` | `dl` 是 DelegateIDs（委托），`dd` 才是截止日期 |
| **时间戳** | 毫秒（`×1000`） | **秒级（float）** | `Timestamp` (UnixNano/1e9) | Things Cloud 用秒级 Unix 时间戳（带小数） |

同时新增了遗漏的 **`md`（modification date 修改日期）** 字段到 Task6 payload。

#### 🪟 原生 Windows 桌面窗口（pywebview）

| 项目 | v1.2.x | v2.0.0 |
|---|---|---|
| 启动方式 | 后端 + 自动打开浏览器 | 原生窗口（内嵌 WebView2） |
| 界面载体 | Chrome/Edge 浏览器 | **原生 Windows 窗口** |
| 地址栏 | 有 | **无（纯应用界面）** |
| 窗口管理 | 浏览器标签页 | **独立应用窗口** |
| 打包方式 | PyInstaller `--noconsole` | PyInstaller `--windowed` |
| 依赖 | HTTP + 浏览器 | HTTP + WebView2 运行时 |

**架构变化：**
- 新增 `main_window.py` —— 在同一进程内用守护线程启动后端 + pywebview 原生窗口
- 关闭窗口自动退出进程（后端线程自动清理）
- 端口冲突时自动 +1（和之前一样）

#### 📦 交付物

**原生窗口版（推荐）：**
| 文件 | 说明 |
|---|---|
| `dist/ThingsWindows.exe` | **v2.0.0 原生桌面版**（双击即开原生窗口） |
| `releases/v2.0.0/ThingsWindows_v2.0.0.exe` | 归档版 |

**纯网页版（备用）：**
| 文件 | 说明 |
|---|---|
| `app.py` + `index.html` + `things_cloud.py` | 源码模式：`python app.py` → 浏览器打开 `http://localhost:55234` |

#### 🔧 向后兼容

- 读操作（`_format_task_full`）已兼容新旧字段（`tt or ti`, `dd or dl`）
- Things Cloud 对旧字段可能有容错，但 iOS 3.x 客户端**依赖正确字段**才能显示
- iOS Things 3.21.8 同步时不会弹更新提示（header/CLIENT_INFO 伪装不变）

---

## v1.2.1 — 2026-10-04

### 🖥 静默启动：双击不再弹出黑色控制台窗口

**用户反馈：** 双击 exe 后有一个黑色命令行弹窗，希望能隐藏掉。

**改动：**

| 项目 | v1.2.0 | v1.2.1 |
|---|---|---|
| PyInstaller 参数 | `--onefile --console` | `--onefile --noconsole` |
| 日志输出 | `print(..., file=sys.stderr)` | `logging` 写入 `things_debug.log` 文件 |
| 双击行为 | 黑色控制台弹窗 + 浏览器 | 仅浏览器，无弹窗 |
| 调试方式 | 看控制台 | 打开 `dist\things_debug.log` |
| 停止方式 | 关控制台窗口 | 任务管理器搜 `ThingsWindows` → 结束任务 |

**日志文件位置：** `dist\things_debug.log`（和 exe 同目录），内容和之前控制台看到的一样：
```
[15:52:10] [INFO] Things Windows v1.2.1 启动, 日志文件: D:\...\things_debug.log
[15:52:20] [INFO] [commit] ancestor=500 items=1 schema=201 appid=com.culturedcode.ThingsiPhone
[15:52:20] [INFO] [commit] attempt=1 HTTP=200
[15:52:20] [INFO] [commit] ✅ 成功 new_head=501
```

如果需要看控制台调试（开发时），可以：
- 直接 `python app.py` 跑源码 → 有控制台
- 或者 `cmd.exe /c dist\ThingsWindows.exe` → 有控制台（虽然是 noconsole 模式但 cmd 会保留窗口）

### 📦 交付物

| 文件 | 说明 |
|---|---|
| `dist/ThingsWindows.exe` | **v1.2.1 静默版**（无弹窗，日志写文件） |
| `dist/ThingsWindows_v1.2.1_silent.exe` | 带版本号后缀 |
| `启动.bat` | 已更新为 v1.2.1 |
| `dist/things_debug.log` | 运行后自动生成的日志文件 |

---

## v1.2.0 — 2026-10-04

### 🔥 重大修复：commit 双向同步 + iPhone 停止弹更新 + 快速点击不再丢

本版本集中解决了 **4 个跨版本积累的核心问题**：

---

### 🔧 修复 1：iPhone Things 3.21.8 停止弹"必须更新"（v1.1.7 没完全修好）

**根因：** v1.1.7 只改了 SCHEMA_HEADER / APP_ID / UA / Task6 格式，
但忘了改 `CLIENT_INFO` —— Things Cloud 会把每个客户端的完整 CLIENT_INFO 通知给所有设备：

```json
// v1.1.7 CLIENT_INFO (iPhone 看到会强制弹更新):
{
  "nn": "ThingsCloudPython",     ← "这是个陌生客户端!"
  "nv": "32209501",              ← "版本比我 3.21.8 高!"
  "on": "Windows",
  "dm": "Windows11"
}
```

**v1.2.0 修复：** 彻底伪装成 Things 3.21.8 iOS：

```json
{
  "dm": "iPhone14,2",
  "nn": "ThingsiPhone",
  "nv": "32108",
  "on": "iOS",
  "ov": "16.0"
}
```

iPhone Things 3.21.8 从 sync 里看到这个客户端信息 → **"哦，是另一个 Things 3.21.8 iOS"** → 不弹更新了。

---

### 🔧 修复 2：commit 真正同步到 Things Cloud（之前可能"假装成功"）

v1.1.8 及之前 mark_task_status / trash_task 每次 commit 前都要 `get_history_head()`
从服务器拉 ancestor_index。问题：

```
t=0ms: get_history_head → ancestor=500
t=10ms: commit(ancestor=500) → 成功, head 变成 501
t=20ms: 用户快速点第二次
t=20ms: get_history_head → ancestor=501 ✅ (这次是对的)
       但是在网络快的时候，有时两次 get_history_head 返回一样的值 → 409 冲突
       然后 commit 抛异常 → 前端收到 502 → 显示"已完成"是前端的假成功提示
```

**v1.2.0 修复：** 用 `things._head_index` 缓存 + commit 返回新 head_index：

```python
ancestor = things._head_index    # 优先用缓存
new_head = commit(ancestor)      # commit 返回新 index
things._head_index = new_head    # 缓存更新，下一次直接用
```

快速连续点击 3 次 → 3 次 commit 全部成功，ancestor 从 500→501→502→503 递增。

---

### 🔧 修复 3：commit 加了详细日志（方便诊断）

`commit()` 函数现在会把每次请求打印到 stderr：

```
[commit] ancestor=500 items=1 schema=201 appid=com.culturedcode.ThingsiPhone
[commit] attempt=1 HTTP=200
[commit] ✅ 成功 new_head=501
```

如果失败会打印：
```
[commit] ❌ HTTP 409: {"latest-server-index": 502}   ← 看到冲突原因
```

**用户可以从控制台直接看到 commit 到底是 200 成功还是 409 冲突。**

---

### 🔧 修复 4：快速点击 3 次才消失（根本原因是 ancestor 缓存）

和修复 2 是同一个根因。v1.1.5 改成了缓存直改让前端立即消失，
但后台 commit 在快速点击时会因为 ancestor 过期而 409。
用户看到前端"消失了"（缓存直改生效），但手机端"没变化"（云端 commit 被服务器拒绝）。
要点 3 次才能"碰运气"等到服务器没冲突。

**v1.2.0 修复后：** 缓存直改 + commit 缓存 head_index →
**1 次点击 → 前端立即消失 + 云端立即同步 + iPhone 几秒后看到**。

---

### 📦 交付物

| 文件 | 说明 |
|---|---|
| `dist/ThingsWindows.exe` | v1.2.0 主程序 |
| `dist/ThingsWindows_v1.2.0.exe` | 带版本号后缀 |
| `启动.bat` | 已更新为 v1.2.0 |

### 🚀 使用

**关掉所有旧 ThingsWindows** → **双击 `启动.bat`** → 登录 → **Ctrl+Shift+R 强刷一次**

### 🧪 测试清单

| # | 操作 | 预期结果 |
|---|---|---|
| 1 | 在 Windows 勾选一个待办 | ✅ 立即消失 |
| 2 | 等 3-10 秒 | ✅ iPhone Things 3.21.8 里它进日志簿 |
| 3 | iPhone 上改一个任务状态 | ✅ Windows 刷新后看到 |
| 4 | Windows 新建一个任务 | ✅ iPhone 几秒后看到（不弹"必须更新"） |
| 5 | 打开 iPhone Things 3.21.8 | ✅ **不再弹"必须更新"** |

---

## v1.1.8 — 2026-10-04

### 🐛 修复：勾选/删除还要点两次（v1.1.5 缓存直改被 v1.1.4 遗留代码对冲）

**根因：** v1.1.5 改成 commit 后**直接改本地内存缓存**（毫秒级生效），
但忘记删掉 v1.1.4 在**路由层**留下的 `t._tasks = None`：

```
# mark_task_status() —— v1.1.5 正确做法:
commit ✅ → 改缓存 t["human_status"] = "completed" ✅

# 路由层 —— v1.1.4 遗留的多余代码:
if ok: t._tasks = None  ← 立刻把缓存清掉！❌

# 结果:
前端 fetchTasks → _tasks=None → sync() 拉最新 → 云端延迟 → 还是旧数据 → 要点第二次
```

**修复：** 删掉 `/api/tasks/complete`、`/api/tasks/trash`、`/api/dedupe/apply`
这三个路由里多余的 `t._tasks = None`。缓存直改 + 不清缓存 = **一次点击立即生效**。

### 📦 交付物

| 文件 | 说明 |
|---|---|
| `dist/ThingsWindows.exe` | v1.1.8 主程序 |
| `dist/ThingsWindows_v1.1.8.exe` | 带版本号后缀 |
| `启动.bat` | 已更新为 v1.1.8 |

---

## v1.1.7 — 2026-10-04

### 🎖 兼容性关键修复：iPhone Things 3.21.8 不再弹"必须更新"

**根因：** 我们的 Windows 程序伪装成了 **Things 4 / Mac 客户端**：

| 配置项 | v1.1.6 错误值 | v1.1.7 正确值 |
|---|---|---|
| `SCHEMA_HEADER` | `"301"` (Things 4) | `"201"` (Things 3.x) |
| `THINGS_APP_ID` | `com.culturedcode.ThingsMac` | `com.culturedcode.ThingsiPhone` |
| `THINGS_USER_AGENT` | `ThingsMac/32209501` | `ThingsiPhone/32108` (对应 3.21.8) |
| commit 格式 | Task7 为主 + Task6 fallback | **只用 Task6** |

iPhone Things 3.21.8 看到 schema=301 或 Task7 条目 → 认为有新客户端在同步 →
强制弹 **"您在另一台设备上使用了新版本的 Things"** → 用户被迫点"稍后"或"更新"（但升不了）。

**修复：** 彻底伪装成 Things 3.21.x iOS 客户端：
1. Schema header 降到 `"201"` (Things 3.x 的协议版本)
2. App-Id 改成 iPhone 的 `com.culturedcode.ThingsiPhone`
3. User-Agent 对应 Things 3.21.8
4. 所有 commit / 修改 / 删除 **只用 Task6 格式**，完全去掉 Task7

**验证方式：** 用 v1.1.7 在 Windows 上改一个任务 → iPhone Things 3.21.8 打开 → **不再弹"必须更新"**。

### 📦 交付物

| 文件 | 说明 |
|---|---|
| `dist/ThingsWindows.exe` | v1.1.7 主程序 |
| `dist/ThingsWindows_v1.1.7.exe` | 带版本号后缀 |
| `启动.bat` | 已更新为 v1.1.7 |

---

## v1.1.6 — 2026-10-04

### 🔐 重要修复：多设备并发写入冲突自动重试 + 老版本 Things 3 兼容

**根因：** Things Cloud 的 commit 使用 `ancestor-index` 做乐观并发控制。
当 Windows 和 iPhone **几乎同时**修改同一个任务时，手机端先 push → 后端 head 前进 → Windows 的 ancestor 过期 →
返回 **HTTP 409 Conflict**。旧代码直接抛异常，导致 Windows 的修改丢失或整个操作失败。

Cultured Code 自家的 Mac/iOS 客户端遇到 409 会自动拿新 ancestor 重试，我们之前没做这个逻辑。

**修复：** `ThingsClient.commit()` 重写为自动冲突重试：
```
for attempt in range(5):
    resp = _post(..., ancestor_index=ancestor)
    if 200: 成功
    if 409: 从 resp.json 或 get_history_head 拿新 ancestor → 重试
    其他: 抛异常
5 次后还冲突 → 明确报错请稍后再试
```

### 📱 老版本 Things 3 兼容性说明

Things Cloud 协议**向后兼容**，不要求所有客户端同版本：

| 客户端版本 | commit 格式 | 兼容性 |
|---|---|---|
| Things 3.x (iPhone 你的版本) | Task6 | ✅ 能读能写 Task6 + Task7 |
| Things 4.x / Things 2026 | Task7 + Fractus | ✅ 能读能写 Task6 + Task7 |
| **Windows v1.1.6** | Task6 为主 + Task7 fallback | ✅ 同时兼容老/新客户端 |

**唯一注意点：** 如果你手机上的 Things 3 **非常老**（< 3.15，2021 年之前），
可能不识别 `deadline_date` 字段在 sync 时的新命名，但不会丢失数据——
Cultured Code 后端会自动做字段映射。

### 📦 交付物

| 文件 | 说明 |
|---|---|
| `dist/ThingsWindows.exe` | v1.1.6 主程序 |
| `dist/ThingsWindows_v1.1.6.exe` | 带版本号后缀 |
| `启动.bat` | 已更新为 v1.1.6 |

---

## v1.1.5 — 2026-10-04

### 🚀 关键优化：勾选/删除任务立即生效（零延迟本地缓存直改）

**根因：** Things Cloud 的 commit → history 同步有 **最终一致性延迟**（几百毫秒到几秒）。
v1.1.4 的方案是 commit 后 `t._tasks = None` 强制重新 sync()，但 sync 回来的还是旧数据——
刚推的 commit 还没出现在云端 history 里。所以必须**点好几次**才能"碰运气"等到云端同步完成。

**修复：** 不再依赖云端最终一致。commit 成功后**直接在本地内存 `_tasks` 缓存里修改那条任务**：

| 操作 | 本地缓存即时修改 |
|---|---|
| `mark_task_status` (完成/取消/恢复) | 直接改 `human_status` + `status` 字段 |
| `trash_task` (单条删除) | 直接从 `_tasks` 列表里 `filter` 掉 |
| `trash_tasks_batch` (批量删除) | 同上，一次 filter 批量移除 |

前端 `fetchTasks()` 拿到的就是修改后的缓存 → 任务立刻消失 ✅ 不用再 sync。

**云端一致性保障：** 改动仍然 commit 到 Things Cloud，手机/iPad 那边下次 sync 会拿到。

### 📦 交付物

| 文件 | 说明 |
|---|---|
| `dist/ThingsWindows.exe` | v1.1.5 主程序 |
| `dist/ThingsWindows_v1.1.5.exe` | 带版本号后缀 |
| `启动.bat` | 已更新为 v1.1.5 |

---

## v1.1.4 — 2026-10-04

### 🐛 关键修复：勾选完成 / 删除后任务不消失（内存缓存未重置）

**根因：** `app.py` 里 `/api/tasks/complete`、`/api/tasks/trash`、`/api/dedupe/apply` 成功 commit 到 Things Cloud
后，忘了清空 `Things._tasks` 内存缓存。结果前端 `fetchTasks()` 重新拉列表时，`get_tasks()` 直接返回旧缓存，
任务看起来"完成了但没消失"。

对比 `add_task` 里正确做了 `self._tasks = None`，但 app.py 的三个写接口漏了。

**修复：** 三个写接口在 commit 成功后都加 `t._tasks = None`，强制下次 `get_tasks()` 重新 `sync()` 拉最新。

### 📦 交付物

| 文件 | 说明 |
|---|---|
| `dist/ThingsWindows.exe` | v1.1.4 主程序 |
| `dist/ThingsWindows_v1.1.4.exe` | 带版本号后缀 |
| `启动.bat` | 已更新为 v1.1.4 |

---

## v1.1.3 — 2026-10-04

### 🐛 关键修复：勾选完成 / 删除 / 新建任务时报 `unexpected keyword argument 'params'`

**根因：** `things_cloud.py` 的 `ThingsClient.commit()` 里调 `self._post(..., params={...})` 传了
`params` 参数，但 `_post` 的函数签名里没有定义这个参数：

```python
# 原来
def _post(self, path: str, body: dict, extra_headers: dict | None = None)

# 调用处
resp = self._post(..., params={"ancestor-index": ancestor_index, "_cnt": len(items)})
```

结果：任何写操作（complete / trash / add / dedupe）触发 commit 时都会抛 `TypeError`。

**修复：** 给 `_post` 加 `params: dict | None = None` 参数，并正确透传到 `session.post()`：

```python
def _post(self, path, body, extra_headers=None, params=None):
    return self.session.post(..., params=params, ...)
```

### 📦 交付物

| 文件 | 说明 |
|---|---|
| `dist/ThingsWindows.exe` | v1.1.3 主程序 |
| `dist/ThingsWindows_v1.1.3.exe` | 带版本号后缀 |
| `启动.bat` | 已更新为 v1.1.3 |

---

## v1.1.2 — 2026-10-04

### 🐛 关键修复：所有任务显示 ✓ 已完成（前端硬编码 bug）

**根因：** index.html 第 134 行按钮里的 `✓` 是**硬编码**的，不管 `human_status` 是什么都画 ✓！

```html
<button ... :class="... ? 'bg-green-500' : ...">
  ✓   <!-- 永远显示！不管 pending 还是 completed！ -->
</button>
```

**修复：** 按 `human_status` 条件渲染图标：
- `completed` → 绿色背景 + ✓（加删除线 + 灰色文字）
- `canceled` → 灰色背景 + ✕
- `pending` → 空心圆圈（无边框，hover 变蓝）

**后端诊断确认：** 后端逻辑 100% 正确（今天 193 条全部 `pending`，360 pending / 743 completed / 33 canceled），
问题全在前端。

### 📦 交付物

| 文件 | 说明 |
|---|---|
| `dist/ThingsWindows.exe` | v1.1.2 主程序 |
| `dist/ThingsWindows_v1.1.2.exe` | 带版本号后缀 |
| `启动.bat` | 已更新为 v1.1.2 |

---

## v1.1.1 — 2026-10-04

### 🐛 修复：侧边栏列表排序混乱（最新日期应在最上面）

v1.1.0 之前 `filter_tasks()` 返回的就是 Things Cloud sync 的原始顺序（协议侧序不是按日期），导致
同日期任务散在各处。比如「买电脑 10/4」跑到「洗车 10/3」下面。

**修复：** 在 `filter_tasks()` 末尾加统一排序：
- 有 `scheduled_ms` → 按日期倒序（新日期在上）
- 无 `scheduled_ms` → 按 `created_ms` 倒序（排在有日期的后面）

---

## v1.1.0 — 2026-10-04

### ✨ 新功能（对齐 iOS Things 3 侧边栏）

iOS Things 3 有 6 个主列表，v1.0.2 只有 3 个。v1.1.0 完整补齐：

| 侧栏列表 | Icon | 说明 | filter_tasks 逻辑 |
|---|---|---|---|
| 📥 收件箱 | inbox | 刚捕获的想法，还没分类 | st=0（无任何调度） |
| ☀️ 今天 | today | 今天要完成的事 | st=1/2 且 sr ≤ 今天 |
| 📂 **计划** 🆕 | projects | 所有项目分组 | type=project 且 pending |
| ⏰ **随时** 🆕 | anytime | 随时可以做的事 | st=1 且 sr 为空 或 sr > 今天 |
| ⏳ 某天 | someday | 以后再说的事 | st=2 且 sr > 今天 |
| 📖 **日志簿** 🆕 | logbook | 已完成 + 已取消 | human_status in (completed, canceled) |
| 📋 全部 | all | 所有待办任务 | pending 的并集 |

### 🔧 技术改动

- `things_cloud.py` — `filter_tasks()` 加 3 个新 case：`projects` / `logbook` / `anytime`（独立列表，和 today 分开）
- `app.py` — 新增 `/api/stats` 接口，一次返回所有 7 个列表的 count（登录后前端自动 fetch）
- `index.html` — 侧边栏重写：从 `/api/stats` 拿准确 count，6 项全齐；`currentTitle` / `currentSubtitle` 同步扩展
- 登录成功后自动调用 `fetchStats()` → `fetchTasks()`，侧边栏 count 实时更新

### 📦 交付物

| 文件 | 大小 |
|---|---|
| `dist/ThingsWindows.exe` | 14.4 MB (v1.1.0) |
| `dist/ThingsWindows_v1.1.0.exe` | 同上（带版本号后缀方便识别） |
| `启动.bat` | 已更新为 v1.1.0 |

---

## v1.0.2 — 2026-10-04

### 🐛 关键修复（必须升级）

- **时间显示修复**：`sr/sp/dd` 字段是**秒级**时间戳（如 1762560000 = 2025-11-08），旧代码除以 1000 按毫秒算导致所有日期显示为 `1970-01-21`。新函数 `_ts_to_date()` 自动识别秒/毫秒（>1e12 为毫秒）
- **列表过滤完全重写**：旧代码把 `today` 和 `anytime` 混为一谈（都用 `schedule == "anytime"`），导致：
  - 今天列表塞满 252 条（任何 st=1 都进来）→ 正确 193 条（仅 sr ≤ 今天）
  - 收件箱显示 0 条 → 正确 9 条
  - Someday 永远显示 0 条
  - 已完成/已取消任务显示在待办里
  新版按 Things 真实语义判断：
  - Inbox = st=0（无任何调度）
  - Today = st=1/2 且 sr ≤ 今天（含过期任务）
  - Anytime = st=1 且（sr 为空 或 sr > 今天）
  - Someday = st=2 且 sr > 今天

### 🛡 健壮性提升

- `_send_json()` 和静态资源响应都加了 `Cache-Control: no-cache`，避免浏览器缓存旧版前端代码导致白屏/数据错乱
- 新增 `/api/debug/full` 诊断接口，返回完整 rebuilt state 的 st_code/schedule/human_status 分布，快速定位同步问题

### 📦 交付物

| 文件 | 说明 |
|---|---|
| `dist/ThingsWindows.exe` | 单文件 exe，~14 MB |
| `启动.bat` | 一键启动（优先 exe，回退 Python 源码） |
| `releases/v1.0.1/` | 上一个版本归档 |

---

## v1.0.1 — 2026-10-04

### 🐛 Bug 修复（必须升级）

- **修复登录后任务列表全空的问题**（核心 bug）
  - Things Cloud 新版 "Fractus" 同步协议中，`ti`(标题)、`nt`(备注) 等字段返回类型可能是 `dict`/`list` 而非 `str`
  - 旧代码直接调用 `.strip()` 导致 `AttributeError: 'dict' object has no attribute 'strip'`
  - 新增 `_safe_str()` / `_safe_int()` / `_safe_bool()` / `_safe_list()` 系列安全解析器，自动兼容 str / dict / list / int / bool 各种返回格式
  - `_rebuild_state()` 加入单条容错，坏数据不再阻断全量重建

- **端口自动避让逻辑**（之前 8765 被百度输入法 baidupinyin.exe 固定占用）
  - 默认端口改为 `55234`，不再和输入法冲突
  - `_try_bind()` 自动扫描端口冲突，被占则 +1 顺延（最多 20 次）

- **Windows GBK 控制台编码修复**
  - app.py 启动时自动 reconfigure stdout/stderr 为 UTF-8，emoji 不再乱码

### ✨ 新功能

- **诊断接口** `GET /api/debug/sync` —— 用于排查同步问题，返回 raw_count / rebuilt_count / kind 分布 / payload 字段名 / 前 10 条原始样本
- **UI 新增「已完成」视图** —— 侧边栏可查看历史已完成任务
- **侧边栏任务计数** —— 实时显示 inbox / today / someday 的待办数量

### 🔧 内部改进

- `_rebuild_state()` 核心重建逻辑重写：`Action 0` 同时视为 created；`Task4/Task3/Task` 系列也纳入处理；payload 非 dict 类型自动兜底为空
- PyInstaller 打包使用 `--add-data` 正确嵌入 `index.html`，修复 `sys._MEIPASS` 资源路径
- 项目目录引入 `releases/` 归档体系 + `CHANGELOG.md`

### 📦 交付物

| 文件 | 说明 |
|---|---|
| `dist/ThingsWindows.exe` | 单文件 exe，14.4 MB |
| `启动.bat` | 一键启动（优先 exe，回退 Python 源码） |
| `releases/v1.0.0/` | 上一个版本归档 |

---

## v1.0.0 — 2026-10-03

首个公开版本。

### ✨ 主要功能

- Things Cloud 账号登录（邮箱 + 密码）
- 从 Things Cloud Sync 拉取全部历史，重建为当前任务状态
- Web 界面：收件箱 / 今天 / 某天 / 全部 列表
- 新建任务：支持标题、时间（today/evening/tomorrow/someday/指定日期）、截止日期、备注、标签
- 标记完成 / 移入垃圾桶
- **自动去重**：扫描完全相同 + 标准化后相同的任务组，自动保留最早创建的，一键清除其余
- 任务详情面板（右侧抽屉）
- 全局搜索（标题 + 备注）
- PyInstaller 单文件 exe 打包（Windows 7+）

### 📦 交付物

- `dist/ThingsWindows.exe` — 单文件 exe（PyInstaller --onefile）
- `things_cloud.py` — 核心 API 库（ThingsClient / Things / Base58 UUID / sync / commit）
- `app.py` — Web 后端（纯标准库 http.server，零依赖）
- `index.html` — Vue 3 + Tailwind CSS 单页前端
- `things_cli.py` — 命令行版（供 Quicker 等外部工具调用）

### 🔒 版权声明

本项目通过 Things Cloud 官方同步协议（`cloud.culturedcode.com` 后端 API）访问用户自有数据，协议由社区逆向工程还原（`arthursoares/things-cloud-sdk`、`evanpurkhiser/things3-cloud` 等开源项目参考实现）。**仅限个人非商业化使用。** 请勿用于任何违反 Cultured Code 服务条款的场景。

