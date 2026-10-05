# -*- coding: utf-8 -*-
"""
安全凭证存储 — 设备指纹 + DPAPI 加密 + 二次验证

三层防护:
  1. DPAPI (Windows Data Protection API): 加密密码, 绑定当前 Windows 用户 + 当前机器
  2. 设备指纹 (Machine GUID): 拷到别的电脑 → 指纹不匹配 → 不认旧存储
  3. 二次验证 PIN: 同电脑同用户打开 EXE → 还要再输一次 PIN

存储位置: %APPDATA%/ThingsWindows/credentials.dat
"""
import hashlib
import hmac
import json
import os
import sys
import time
import base64

# Windows-only imports
try:
    import winreg
    import win32crypt
    DPAPI_AVAILABLE = True
except ImportError:
    DPAPI_AVAILABLE = False

APP_NAME = "ThingsWindows"


def _get_appdata_dir() -> str:
    """返回 %APPDATA%/ThingsWindows, 确保目录存在。"""
    if sys.platform == "win32":
        base = os.environ.get("APPDATA", os.path.expanduser("~"))
    else:
        base = os.path.expanduser("~")
    d = os.path.join(base, APP_NAME)
    os.makedirs(d, exist_ok=True)
    return d


CRED_FILE = os.path.join(_get_appdata_dir(), "credentials.dat")


# ============================================================
# 设备指纹 (Windows Machine GUID — 每台机器唯一)
# ============================================================

def get_device_fingerprint() -> str:
    """
    获取当前机器的唯一指纹。
    Windows: MachineGuid (注册表 HKLM\...\Cryptography)
    跨平台兜底: MAC 地址 hash
    """
    if sys.platform == "win32":
        try:
            key = winreg.OpenKey(
                winreg.HKEY_LOCAL_MACHINE,
                r"SOFTWARE\Microsoft\Cryptography"
            )
            guid, _ = winreg.QueryValueEx(key, "MachineGuid")
            winreg.CloseKey(key)
            return guid.strip()
        except Exception:
            pass

    # 兜底: 用 MAC 地址
    try:
        import uuid as uuid_mod
        mac = uuid_mod.getnode()
        return hashlib.sha256(f"mac:{mac}".encode()).hexdigest()[:32]
    except Exception:
        return "unknown-device"


# ============================================================
# DPAPI 加密 / 解密
# ============================================================

def dpapi_encrypt(plaintext: bytes) -> bytes:
    """DPAPI 加密 — 绑定当前 Windows 用户 + 当前机器。"""
    if not DPAPI_AVAILABLE:
        # 跨平台兜底: 简单 XOR + 设备指纹 (弱, 但聊胜于无)
        fp = get_device_fingerprint().encode()
        out = bytearray()
        for i, b in enumerate(plaintext):
            out.append(b ^ fp[i % len(fp)])
        return b"fallback-v1:" + bytes(out)
    # pywin32 CryptProtectData(data, desc, entropy, reserved, promptstruct, flags)
    return win32crypt.CryptProtectData(plaintext, None, None, None, None, 0)


def dpapi_decrypt(ciphertext: bytes) -> bytes:
    """DPAPI 解密 — 拷到别的电脑会抛异常。"""
    if ciphertext.startswith(b"fallback-v1:"):
        # 跨平台兜底
        fp = get_device_fingerprint().encode()
        data = ciphertext[len(b"fallback-v1:"):]
        out = bytearray()
        for i, b in enumerate(data):
            out.append(b ^ fp[i % len(fp)])
        return bytes(out)
    if not DPAPI_AVAILABLE:
        raise RuntimeError("win32crypt 不可用, 无法解密")
    # pywin32 CryptUnprotectData(data, entropy, reserved, promptstruct, flags)
    result = win32crypt.CryptUnprotectData(ciphertext, None, None, None, 0)
    return result[1]  # decrypted bytes


# ============================================================
# 二次验证 PIN (PBKDF2-HMAC-SHA256)
# ============================================================

def hash_pin(pin: str, salt: bytes | None = None) -> tuple[str, bytes]:
    """对 PIN 做 PBKDF2 哈希 → 返回 (base64哈希, salt)。"""
    if salt is None:
        salt = os.urandom(16)
    dk = hashlib.pbkdf2_hmac("sha256", pin.encode(), salt, 100_000, dklen=32)
    return base64.b64encode(dk).decode(), salt


def verify_pin(pin: str, stored_hash_b64: str, salt_b64: str) -> bool:
    """验证 PIN 是否匹配。"""
    salt = base64.b64decode(salt_b64)
    expected = base64.b64decode(stored_hash_b64)
    dk = hashlib.pbkdf2_hmac("sha256", pin.encode(), salt, 100_000, dklen=32)
    return hmac.compare_digest(dk, expected)  # 时序安全比较


# ============================================================
# 高层: 读 / 写 / 删
# ============================================================

def save_credentials(email: str, password: str, pin: str | None = None):
    """
    保存凭证到本机。
    password → DPAPI 加密
    pin → PBKDF2 哈希 (如果提供)
    """
    device_fp = get_device_fingerprint()
    password_enc = dpapi_encrypt(password.encode())
    password_enc_b64 = base64.b64encode(password_enc).decode()

    record = {
        "v": 1,                           # 存储格式版本
        "device_fp": device_fp,           # 记录时的设备指纹
        "email": email,
        "password_enc": password_enc_b64,  # DPAPI 加密
        "created_at": time.time(),
        "2fa_enabled": bool(pin),
    }
    if pin:
        h, salt = hash_pin(pin)
        record["2fa_hash"] = h
        record["2fa_salt"] = base64.b64encode(salt).decode()

    with open(CRED_FILE, "w", encoding="utf-8") as f:
        json.dump(record, f, indent=2)


def load_credentials() -> dict | None:
    """
    读取凭证。返回 None 表示: 文件不存在 / DPAPI 解密失败 / 设备指纹不匹配。
    返回 dict: {"email": str, "password": str (解密后), "2fa_enabled": bool, "stored_email": str}
    """
    if not os.path.isfile(CRED_FILE):
        return None

    try:
        with open(CRED_FILE, "r", encoding="utf-8") as f:
            rec = json.load(f)

        # 检查设备指纹
        current_fp = get_device_fingerprint()
        if rec.get("device_fp") != current_fp:
            # 拷到别的电脑了 → 不认
            return None

        # DPAPI 解密密码
        password_enc = base64.b64decode(rec["password_enc"])
        password = dpapi_decrypt(password_enc).decode()

        return {
            "email": rec["email"],
            "password": password,
            "2fa_enabled": rec.get("2fa_enabled", False),
            "2fa_hash": rec.get("2fa_hash"),
            "2fa_salt": rec.get("2fa_salt"),
        }
    except Exception:
        # DPAPI 解密失败 (换电脑 / 换 Windows 用户 / 文件损坏)
        return None


def has_remembered() -> dict:
    """
    快速检查有没有记住的凭证 (不返回密码)。
    返回: {"has": bool, "email": str or None, "2fa": bool}
    """
    if not os.path.isfile(CRED_FILE):
        return {"has": False, "email": None, "2fa": False}

    try:
        with open(CRED_FILE, "r", encoding="utf-8") as f:
            rec = json.load(f)

        current_fp = get_device_fingerprint()
        if rec.get("device_fp") != current_fp:
            return {"has": False, "email": None, "2fa": False}

        # 验证 DPAPI 还能不能解密 (试探)
        try:
            test = base64.b64decode(rec["password_enc"])
            dpapi_decrypt(test)
        except Exception:
            return {"has": False, "email": None, "2fa": False}

        return {
            "has": True,
            "email": rec["email"],
            "2fa": rec.get("2fa_enabled", False),
        }
    except Exception:
        return {"has": False, "email": None, "2fa": False}


def remove_credentials():
    """删除本机保存的凭证。"""
    try:
        if os.path.isfile(CRED_FILE):
            os.remove(CRED_FILE)
    except Exception:
        pass


def verify_2fa(pin: str) -> bool:
    """验证 2FA PIN。需要先 load_credentials() 拿 hash/salt。"""
    rec = load_credentials()
    if not rec or not rec["2fa_enabled"]:
        return False
    return verify_pin(pin, rec["2fa_hash"], rec["2fa_salt"])
