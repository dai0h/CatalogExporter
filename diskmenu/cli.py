"""命令行入口：list / scan / export / delete / clear / gui / tray / install / uninstall。"""

from __future__ import annotations

import argparse
from datetime import datetime
import sys
from typing import Optional

from . import __version__, db, exporter
from .paths import db_path as default_db_path


def _conn(db_path: Optional[str]):
    conn = db.connect(db_path)
    db.init_db(conn)
    return conn


def _fmt_size(size: int) -> str:
    if size < 1024:
        return f"{size} B"
    units = ["KB", "MB", "GB", "TB", "PB"]
    value = float(size)
    for unit in units:
        value /= 1024.0
        if value < 1024 or unit == units[-1]:
            return f"{value:.1f} {unit}"
    return f"{size} B"


def _fmt_time(ts: Optional[int]) -> str:
    if not ts:
        return "-"
    try:
        return datetime.fromtimestamp(ts).strftime("%Y-%m-%d %H:%M")
    except Exception:
        return "-"


def cmd_list(args) -> int:
    conn = _conn(args.db)
    rows = db.list_disks(conn)
    if not rows:
        print("暂无任何硬盘索引。插入硬盘后程序会自动扫描。")
        return 0
    print(f"{'硬盘 ID':<44} {'名称':<16} {'盘符':<5} {'序列号':<10} {'状态':<10} {'文件数':>10} {'总大小':>12} {'最近扫描':<18}")
    for r in rows:
        name = (r["label"].strip() or "未命名硬盘")[:14]
        print(
            f"{r['disk_id']:<44} {name:<16} {r['drive_letter'] or '-':<5} {r['volume_serial'] or '-':<10} {r['status']:<10} "
            f"{r['total_files']:>10,} {_fmt_size(r['total_size']):>12} "
            f"{_fmt_time(r['last_scan_finished']):<18}"
        )
    conn.close()
    return 0


def cmd_scan(args) -> int:
    from .scanner import scan_disk

    conn = _conn(args.db)
    disk = db.get_disk(conn, args.disk)
    if disk is None:
        print("未找到该硬盘索引。可先用 list 查看现有盘，或插入硬盘后启动托盘程序自动登记。")
        conn.close()
        return 1
    mode = "full" if args.full else "incremental"
    conn.close()
    print(f"开始{('完整' if args.full else '增量')}扫描：{disk['label']} ({disk['drive_letter']})")
    ok, msg = scan_disk(args.disk, mode=mode, db_path=args.db)
    print(msg)
    return 0 if ok else 1


def cmd_export(args) -> int:
    ok, msg = exporter.export_html(args.db, args.disk, args.out)
    print(msg)
    return 0 if ok else 1


def cmd_delete(args) -> int:
    conn = _conn(args.db)
    disk = db.get_disk(conn, args.disk)
    if disk is None:
        print("未找到该硬盘索引。")
        conn.close()
        return 1
    db.delete_disk_index(conn, args.disk)
    conn.close()
    print(f"已删除 {disk['label'] or disk['drive_letter']} 的索引。")
    return 0


def cmd_clear(args) -> int:
    conn = _conn(args.db)
    db.clear_all_indexes(conn)
    conn.close()
    print("已清空全部索引。")
    return 0


def cmd_gui(args) -> int:
    from .entry import start_gui

    start_gui(args.db)
    return 0


def cmd_tray(args) -> int:
    from .entry import start_tray

    start_tray(args.db)
    return 0


def cmd_install(args) -> int:
    from . import autostart

    autostart.install()
    conn = _conn(args.db)
    db.set_setting(conn, "start_at_login", "1")
    conn.close()
    print("已设置开机自动启动。")
    return 0


def cmd_uninstall(args) -> int:
    from . import autostart

    autostart.uninstall()
    conn = _conn(args.db)
    db.set_setting(conn, "start_at_login", "0")
    conn.close()
    print("已取消开机自动启动。")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="catalogexporter", description="目录导出管家")
    parser.add_argument("--db", help="数据库路径（默认在 APPDATA 的 DiskMenu 文件夹下）")
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("list", help="列出所有硬盘索引")
    sub.add_parser("gui", help="打开图形界面")
    sub.add_parser("tray", help="启动后台托盘服务")

    p_scan = sub.add_parser("scan", help="立即扫描一块硬盘")
    p_scan.add_argument("--disk", required=True, help="硬盘 ID（可用 list 查看）")
    p_scan.add_argument("--full", action="store_true", help="完整重新扫描")

    p_export = sub.add_parser("export", help="导出 HTML 离线报告")
    p_export.add_argument("--disk", required=True)
    p_export.add_argument("--out", required=True, help="输出 HTML 文件路径")

    p_del = sub.add_parser("delete", help="删除一块硬盘的索引")
    p_del.add_argument("--disk", required=True)

    sub.add_parser("clear", help="清空全部索引")
    sub.add_parser("install", help="设置开机自启")
    sub.add_parser("uninstall", help="取消开机自启")
    return parser


def main(argv: Optional[list[str]] = None) -> int:
    args = build_parser().parse_args(argv)
    handlers = {
        "list": cmd_list,
        "gui": cmd_gui,
        "tray": cmd_tray,
        "scan": cmd_scan,
        "export": cmd_export,
        "delete": cmd_delete,
        "clear": cmd_clear,
        "install": cmd_install,
        "uninstall": cmd_uninstall,
    }
    return handlers[args.command](args)
