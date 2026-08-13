"""通用小工具。"""

from __future__ import annotations


def safe_filename(name: str) -> str:
    """把字符串转成 Windows 文件名可用的形式。"""
    for ch in '\\/:*?"<>|':
        name = name.replace(ch, "_")
    name = name.strip().strip(".")
    return name[:80] or "Disk"

