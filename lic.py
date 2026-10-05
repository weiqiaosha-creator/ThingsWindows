# -*- coding: utf-8 -*-
"""
授权码验证模块 + CLI 生成器 — ThingsWindows (独立版, 不依赖 auth_store)

绑定: 机器码 (Windows MachineGuid) + 有效期 + HMAC 签名
存储: %APPDATA%/ThingsWindows/license.dat
"""
import base64
import hashlib
import hmac
import json
import os
import struct
import sys
import time

SECRET = b"ThingsWindows-2026-Secret-Key-Change-Me-Anytime"
LICENSE_VERSION = 1
PERMANENT_TS = 4102444799
APP_NAME = "ThingsWindows"


def _get_appdata_dir() -> str:
    if sys.platform == "win32":
        base = os.environ.get("APPDATA", os.path.expanduser("~"))
    else:
        base = os.path.expanduser("~")
    d = os.path.join(base, APP_NAME)
    os.makedirs(d, exist_ok=True)
    return d


LICENSE_FILE = os.path.join(_get_appdata_dir(), "license.dat")


def _get_device_fingerprint() -> str:
    """获取当前机器唯一指纹。Windows: MachineGuid; 兜底: MAC 地址 hash"""
    if sys.platform == "win32":
        try:
            import winreg
            key = winreg.OpenKey(
                winreg.HKEY_LOCAL_MACHINE,
                r"SOFTWARE\Microsoft\Cryptography"
            )
            guid, _ = winreg.QueryValueEx(key, "MachineGuid")
            winreg.CloseKey(key)
            return guid.strip()
        except Exception:
            pass
    import uuid as _uuid
    mac = _uuid.getnode()
    return hashlib.sha256(f"mac:{mac}".encode()).hexdigest()[:32]


def _machine_code_short() -> bytes:
    """取 MachineGuid 的 SHA256 前 8 字节作为机器码"""
    fp = _get_device_fingerprint()
    return hashlib.sha256(fp.encode()).digest()[:8]


def _build_license_payload(machine_code: bytes, expiry_ts: int, version: int = LICENSE_VERSION) -> bytes:
    if len(machine_code) != 8:
        raise ValueError("machine_code 必须是 8 字节")
    return struct.pack(">BI", version, expiry_ts) + machine_code


def _sign(payload: bytes) -> bytes:
    return hmac.new(SECRET, payload, hashlib.sha256).digest()


def _b64url_encode(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()


def _b64url_decode(s: str) -> bytes:
    s = s.rstrip()
    pad = 4 - len(s) % 4
    if pad != 4:
        s += "=" * pad
    return base64.urlsafe_b64decode(s)


def generate_license(machine_code_hex: str, valid_days: int | None = None,
                     expiry_ts: int | None = None) -> str:
    try:
        if len(machine_code_hex) == 16:
            machine_code = bytes.fromhex(machine_code_hex)
        else:
            machine_code = _b64url_decode(machine_code_hex)
            if len(machine_code) != 8:
                raise ValueError("解析后不是 8 字节")
    except Exception as e:
        raise ValueError(f"机器码格式错误 (需要 16 hex 或 8 bytes base64url): {e}")

    if expiry_ts is not None:
        expiry = int(expiry_ts)
    elif valid_days is None or valid_days == 0:
        expiry = PERMANENT_TS
    else:
        expiry = int(time.time()) + int(valid_days) * 86400

    payload = _build_license_payload(machine_code, expiry)
    sig = _sign(payload)
    return _b64url_encode(payload + sig)


def parse_license(license_key: str) -> dict:
    result = {
        "ok": False, "reason": "", "machine_code": "", "expiry_ts": 0,
        "expiry_date": "", "is_permanent": False, "days_remaining": 0,
        "machine_match": False, "signature_valid": False, "expired": False,
    }
    try:
        blob = _b64url_decode(license_key.strip())
    except Exception as e:
        result["reason"] = f"授权码格式错误: {e}"
        return result

    if len(blob) < 41:
        result["reason"] = "授权码过短 (可能被截断)"
        return result

    version = blob[0]
    expiry_ts = struct.unpack(">I", blob[1:5])[0]
    machine_code = blob[5:13]
    signature = blob[13:45]
    expected_sig = blob[0:13]

    recomputed = _sign(expected_sig)
    sig_ok = hmac.compare_digest(recomputed, signature)
    result["signature_valid"] = sig_ok

    current_mc = _machine_code_short()
    result["machine_code"] = machine_code.hex()
    result["machine_match"] = (machine_code == current_mc)

    result["expiry_ts"] = expiry_ts
    result["is_permanent"] = (expiry_ts >= PERMANENT_TS)
    result["expired"] = (not result["is_permanent"] and time.time() > expiry_ts)

    try:
        from datetime import datetime, timezone
        result["expiry_date"] = datetime.fromtimestamp(expiry_ts).strftime("%Y-%m-%d")
    except Exception:
        result["expiry_date"] = "?"

    if result["is_permanent"]:
        result["days_remaining"] = -1
    elif result["expired"]:
        result["days_remaining"] = 0
    else:
        result["days_remaining"] = int((expiry_ts - time.time()) / 86400)

    if not sig_ok:
        result["reason"] = "签名无效 (授权码可能被篡改或来自不信任的来源)"
    elif not result["machine_match"]:
        result["reason"] = "机器码不匹配 (这个授权码是给另一台电脑生成的)"
    elif result["expired"]:
        result["reason"] = "授权已过期, 请联系授权方续费"
    else:
        result["ok"] = True
        result["reason"] = "授权有效"

    return result


def save_license(license_key: str) -> None:
    os.makedirs(os.path.dirname(LICENSE_FILE), exist_ok=True)
    data = {
        "license": license_key,
        "activated_at": time.time(),
        "machine_code": _machine_code_short().hex(),
    }
    with open(LICENSE_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)


def load_license() -> str | None:
    if not os.path.isfile(LICENSE_FILE):
        return None
    try:
        with open(LICENSE_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data.get("license")
    except Exception:
        return None


def clear_license() -> None:
    try:
        if os.path.isfile(LICENSE_FILE):
            os.remove(LICENSE_FILE)
    except Exception:
        pass


def check_local_license() -> dict:
    """检查本地授权 (仅用户手动激活, 无内置 fallback)"""
    key = load_license()
    if key:
        info = parse_license(key)
        info["has_license"] = True
        return info
    return {"ok": False, "reason": "未激活", "has_license": False}


def get_machine_code() -> str:
    return _machine_code_short().hex()


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="ThingsWindows 授权码生成器 (独立 CLI, 无需 auth_store)")
    sub = parser.add_subparsers(dest="cmd")

    g = sub.add_parser("gen", help="生成授权码")
    g.add_argument("machine_code", help="目标机器码 (16 字符 hex)")
    g.add_argument("--days", type=int, help="有效期天数 (永久: 省略或 --days 0)")
    g.add_argument("--expiry", help="直接指定过期日期 YYYY-MM-DD")

    sub.add_parser("machine", help="显示当前机器的机器码 (给授权方用)")

    v = sub.add_parser("verify", help="验证一个授权码")
    v.add_argument("license", help="授权码字符串")

    sub.add_parser("status", help="检查本地已激活的授权状态")

    args = parser.parse_args()

    if args.cmd == "machine":
        mc = get_machine_code()
        print(f"本机机器码: {mc}")
        print("把这个值发给授权方生成授权码")
        print(f"(完整指纹: {_get_device_fingerprint()})")

    elif args.cmd == "gen":
        if args.expiry:
            from datetime import datetime
            ts = int(datetime.strptime(args.expiry, "%Y-%m-%d").timestamp())
            key = generate_license(args.machine_code, expiry_ts=ts)
        else:
            key = generate_license(args.machine_code, valid_days=args.days)

        info = parse_license(key)
        dur_str = "永久" if info["is_permanent"] else f"{info['days_remaining']} 天"
        print()
        print("授权码生成成功:")
        print(f"  机器码:     {info['machine_code']}")
        print(f"  有效期至:   {info['expiry_date']} ({dur_str})")
        print(f"  授权码:")
        print(f"  {key}")
        print()
        print("把上面这一行授权码复制发给使用者即可")

    elif args.cmd == "verify":
        info = parse_license(args.license)
        for k, v in info.items():
            if k == "reason":
                continue
            print(f"  {k}: {v}")
        print(f"  状态: {info['reason']}")

    elif args.cmd == "status":
        print(json.dumps(check_local_license(), indent=2, ensure_ascii=False))

    else:
        parser.print_help()
