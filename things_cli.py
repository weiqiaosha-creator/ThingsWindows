# -*- coding: utf-8 -*-
"""
things_cli — Things Cloud 命令行工具 (Quicker 一键调用友好)

用法示例:
  # 配置认证 (首次)
  python things_cli.py config --email you@example.com --password yourpass

  # 添加任务 (最常用 — 给 Quicker 绑定)
  python things_cli.py add "写周报" --when today
  python things_cli.py add "买牛奶" --when evening --tags "home,errand"
  python things_cli.py add "准备 Q3 报告" --when 2026-09-30 --deadline 2026-10-05 --tags "work"
  python things_cli.py add "项目启动会议" --when tomorrow --notes "地点3楼会议室"

  # 查看任务
  python things_cli.py list today
  python things_cli.py list inbox
  python things_cli.py list all

  # 仅验证认证
  python things_cli.py verify
"""

import argparse
import json
import os
import sys

# config 存储路径 (当前工作目录下)
CONFIG_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "config.json")


def load_config() -> dict:
    if os.path.exists(CONFIG_FILE):
        with open(CONFIG_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}


def save_config(cfg: dict) -> None:
    with open(CONFIG_FILE, "w", encoding="utf-8") as f:
        json.dump(cfg, f, indent=2, ensure_ascii=False)


def get_things(cfg: dict):
    from things_cloud import Things
    email = cfg.get("email")
    password = cfg.get("password")
    history_key = cfg.get("history_key")
    if not email or not password:
        print("❌ 未配置凭据。请先运行: python things_cli.py config --email ... --password ...",
              file=sys.stderr)
        sys.exit(1)
    return Things(email, password, history_key)


def cmd_config(args):
    cfg = load_config()
    if args.email:
        cfg["email"] = args.email
    if args.password:
        cfg["password"] = args.password
    if args.history_key:
        cfg["history_key"] = args.history_key
    save_config(cfg)
    # 如果配置了完整凭据, 顺便 verify 一下
    if cfg.get("email") and cfg.get("password"):
        try:
            from things_cloud import ThingsCloudError, ThingsClient
            c = ThingsClient(cfg["email"], cfg["password"])
            info = c.verify()
            cfg.setdefault("history_key", info["history-key"])
            save_config(cfg)
            print(f"✅ 认证成功! 账户: {info.get('email', '')}")
            print(f"   History Key: {cfg['history_key']}")
        except ThingsCloudError as e:
            print(f"⚠️  配置已保存但认证失败: {e}", file=sys.stderr)
    else:
        print("✅ 配置已保存。")


def cmd_verify(args):
    cfg = load_config()
    try:
        things = get_things(cfg)
        print(f"✅ 连接成功! History Key: {things.history_key}")
    except Exception as e:
        print(f"❌ 连接失败: {e}", file=sys.stderr)
        sys.exit(1)


def cmd_add(args):
    cfg = load_config()
    try:
        things = get_things(cfg)
    except SystemExit:
        raise

    tags = None
    if args.tags:
        tags = [t.strip() for t in args.tags.split(",") if t.strip()]

    uuid = things.add_task(
        title=args.title,
        notes=args.notes,
        when=args.when,
        deadline=args.deadline,
        tags=tags,
    )
    schedule_desc = args.when or "inbox"
    print(f"✅ 已添加:  {args.title}")
    print(f"   时间:    {schedule_desc}")
    if tags:
        print(f"   标签:    {', '.join(tags)}")
    print(f"   UUID:    {uuid}")


def cmd_list(args):
    cfg = load_config()
    things = get_things(cfg)
    tasks = things.get_tasks(args.list_name)

    if not tasks:
        print(f"📭 {args.list_name} 列表为空")
        return

    print(f"📋 {args.list_name} ({len(tasks)} 项)")
    print("-" * 50)
    for i, t in enumerate(tasks, 1):
        # 简短展示
        status_icon = "✅" if t["status"] else "⚪"
        note_hint = f"  📝 {t['notes'][:30]}..." if t["notes"] else ""
        tag_hint = f"  🏷 {' '.join('#' + x for x in t['tags'])}" if t["tags"] else ""
        print(f"{i:>2}. {status_icon} {t['title']}{note_hint}{tag_hint}")


def main():
    parser = argparse.ArgumentParser(
        prog="things_cli",
        description="Things Cloud CLI — Windows 跨平台任务管理工具",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
典型用法 (给 Quicker 调用):
  python things_cli.py add "$%J注$" --when today
  python things_cli.py list today
        """,
    )
    sub = parser.add_subparsers(dest="command", required=True)

    # config
    p_cfg = sub.add_parser("config", help="配置 Things Cloud 凭据")
    p_cfg.add_argument("--email", help="Things Cloud 邮箱")
    p_cfg.add_argument("--password", help="Things Cloud 密码")
    p_cfg.add_argument("--history-key", help="History Key (可选, 首次自动获取)")

    # verify
    sub.add_parser("verify", help="验证认证是否有效")

    # add
    p_add = sub.add_parser("add", help="添加一个新任务")
    p_add.add_argument("title", help="任务标题")
    p_add.add_argument("--notes", "-n", help="备注")
    p_add.add_argument(
        "--when", "-w",
        help="时间: inbox / today / evening / anytime / someday / tomorrow / YYYY-MM-DD",
        default=None,
    )
    p_add.add_argument("--deadline", "-d", help="截止日期 YYYY-MM-DD")
    p_add.add_argument("--tags", "-t", help="标签 (逗号分隔)")

    # list
    p_list = sub.add_parser("list", help="列出任务")
    p_list.add_argument(
        "list_name", nargs="?", default="today",
        choices=["all", "inbox", "today", "anytime", "someday", "upcoming"],
    )

    args = parser.parse_args()

    handlers = {
        "config": cmd_config,
        "verify": cmd_verify,
        "add": cmd_add,
        "list": cmd_list,
    }
    try:
        handlers[args.command](args)
    except KeyboardInterrupt:
        print("\n已取消", file=sys.stderr)
        sys.exit(130)
    except Exception as e:
        print(f"❌ 错误: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
