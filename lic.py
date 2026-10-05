# -*- coding: utf-8 -*-
"""
授权码验证模块 — ThingsWindows

绑定: 机器码 (Windows MachineGuid) + 有效期 + HMAC 签名
存储: %APPDATA%/ThingsWindows/license.dat

生成工具: license_gen.py (授权方使用)
"""
import base64
import hashlib
import hmac
import json
import os
import struct
import sys
import time

# =========================================================================
# 🔐 机密 —— 只有授权方知道这个值, 嵌入到代码里用于签名/验签
# 想换密钥就改这里, 然后重新打包 + 重新发所有授权码
# =========================================================================
SECRET = b"ThingsWindows-2026-Secret-Key-Change-Me-Anytime"

LICENSE_VERSION = 1  # 留版本字节方便未来扩展

# 永久 = 2099-12-31 23:59:59 UTC
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


def _machine_code_short() -> bytes:
    """取当前机器 MachineGuid 的 SHA256 前 8 字节作为机器码"""
    try:
        from auth_store import get_device_fingerprint
        fp = get_device_fingerprint()
    except Exception:
        fp = "unknown-device"
    return hashlib.sha256(fp.encode()).digest()[:8]


def _build_license_payload(machine_code: bytes, expiry_ts: int, version: int = LICENSE_VERSION) -> bytes:
    """构建待签名的原始载荷"""
    if len(machine_code) != 8:
        raise ValueError("machine_code 必须是 8 字节")
    return struct.pack(">BI", version, expiry_ts) + machine_code


def _sign(payload: bytes) -> bytes:
    """HMAC-SHA256 签名"""
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
    """
    生成授权码 (授权方调用)。

    参数:
      machine_code_hex: 目标机器码 (16 字符 hex, 或 8 字节 base64url)
      valid_days:       有效期天数 (None = 永久)
      expiry_ts:        可选, 直接指定 Unix 过期时间戳 (秒级)
    """
    # 解析机器码
    try:
        if len(machine_code_hex) == 16:
            machine_code = bytes.fromhex(machine_code_hex)
        else:
            # 可能是 base64url
            machine_code = _b64url_decode(machine_code_hex)
            if len(machine_code) != 8:
                raise ValueError("解析后不是 8 字节")
    except Exception as e:
        raise ValueError(f"机器码格式错误 (需要 16 hex 或 8 bytes base64url): {e}")

    # 过期时间
    if expiry_ts is not None:
        expiry = int(expiry_ts)
    elif valid_days is None or valid_days == 0:
        expiry = PERMANENT_TS
    else:
        expiry = int(time.time()) + int(valid_days) * 86400

    payload = _build_license_payload(machine_code, expiry)
    sig = _sign(payload)

    blob = payload + sig
    return _b64url_encode(blob)


def parse_license(license_key: str) -> dict:
    """
    解析并验证授权码。

    返回 dict:
      {
        "ok": True/False,
        "reason": str,           # 失败原因 (ok=False 时)
        "machine_code": str,     # 16 字符 hex
        "expiry_ts": int,
        "expiry_date": str,
        "is_permanent": bool,
        "days_remaining": int,   # 剩余天数 (永久 = -1)
        "machine_match": bool,   # 机器码是否匹配当前机器
        "signature_valid": bool, # HMAC 签名是否正确
        "expired": bool,         # 是否已过期
      }
    """
    result = {
        "ok": False,
        "reason": "",
        "machine_code": "",
        "expiry_ts": 0,
        "expiry_date": "",
        "is_permanent": False,
        "days_remaining": 0,
        "machine_match": False,
        "signature_valid": False,
        "expired": False,
    }

    try:
        blob = _b64url_decode(license_key.strip())
    except Exception as e:
        result["reason"] = f"授权码格式错误: {e}"
        return result

    if len(blob) < 41:  # 1 + 4 + 8 + 32 = 45
        result["reason"] = "授权码过短 (可能被截断)"
        return result

    # 拆分
    version = blob[0]
    expiry_ts = struct.unpack(">I", blob[1:5])[0]
    machine_code = blob[5:13]
    signature = blob[13:45]
    expected_sig = blob[0:13]  # payload 就是前 13 字节

    # 签名验证
    recomputed = _sign(expected_sig)
    sig_ok = hmac.compare_digest(recomputed, signature)
    result["signature_valid"] = sig_ok

    # 机器码匹配
    current_mc = _machine_code_short()
    result["machine_code"] = machine_code.hex()
    result["machine_match"] = (machine_code == current_mc)

    # 过期检查
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

    # 综合判断
    if not sig_ok:
        result["reason"] = "签名无效 (授权码可能被篡改或来自不信任的来源)"
    elif not result["machine_match"]:
        result["reason"] = "机器码不匹配 (这个授权码是给另一台电脑生成的)"
    elif result["expired"]:
        result["reason"] = "授权已过期, 请联系授权方续费"
    else:
        result["ok"] = True
        result["reason"] = "授权有效 ✅"

    return result


# ============================================================
# 本地存储
# ============================================================

def save_license(license_key: str) -> None:
    """存激活的授权码到本地"""
    os.makedirs(os.path.dirname(LICENSE_FILE), exist_ok=True)
    data = {
        "license": license_key,
        "activated_at": time.time(),
        "machine_code": _machine_code_short().hex(),
    }
    with open(LICENSE_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)


def load_license() -> str | None:
    """从本地读授权码"""
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
    """一键检查本地授权 (读取 + 验证 + 返回完整状态)"""
    key = load_license()
    if not key:
        return {"ok": False, "reason": "未激活", "has_license": False}
    info = parse_license(key)
    info["has_license"] = True
    return info


def get_machine_code() -> str:
    """返回当前机器码 (16 字符 hex, 给授权方用)"""
    return _machine_code_short().hex()


# ============================================================
# CLI (授权方用)
# ============================================================

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="ThingsWindows 授权码生成器 (CLI)")
    sub = parser.add_subparsers(dest="cmd")

    # 生成
    g = sub.add_parser("gen", help="生成授权码")
    g.add_argument("machine_code", help="目标机器码 (16 字符 hex)")
    g.add_argument("--days", type=int, help="有效期天数 (永久: 省略或 --days 0)")
    g.add_argument("--expiry", help="直接指定过期日期 YYYY-MM-DD")

    # 查本机机器码
    sub.add_parser("machine", help="显示当前机器的机器码")

    # 验证
    v = sub.add_parser("verify", help="验证一个授权码")
    v.add_argument("license", help="授权码字符串")

    # 检查本地
    sub.add_parser("status", help="检查本地已激活的授权状态")

    args = parser.parse_args()

    if args.cmd == "machine":
        print(f"本机机器码: {get_machine_code()}")
        print("把这个值发给授权方生成授权码")

    elif args.cmd == "gen":
        if args.expiry:
            from datetime import datetime
            ts = int(datetime.strptime(args.expiry, "%Y-%m-%d").timestamp())
            key = generate_license(args.machine_code, expiry_ts=ts)
        else:
            key = generate_license(args.machine_code, valid_days=args.days)

        info = parse_license(key)
        if info["is_permanent"]:
            dur_str = "永久"
        else:
            dur_str = f"{info['days_remaining']} 天"
        print(f"\n✅ 授权码生成成功:")
        print(f"   机器码:     {info['machine_code']}")
        print(f"   有效期至:   {info['expiry_date']} ({dur_str})")
        print(f"   授权码:")
        print(f"   ┌─────────────────────────────────────┐")
        print(f"   │  {key}")
        print(f"   └─────────────────────────────────────┘")
        print(f"\n把这一行复制发给使用者即可")

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
