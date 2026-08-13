"""应用路径管理。所有数据默认存放在 %APPDATA%\\DiskMenu。"""

from __future__ import annotations

import os
import sys
from pathlib import Path

APP_NAME = "CatalogExporter"
APP_TITLE = "目录导出管家"
DATA_DIR_NAME = "DiskMenu"  # 保持旧数据目录，避免已有索引失效


def app_data_dir() -> Path:
    base = os.environ.get("APPDATA")
    if base:
        return Path(base) / DATA_DIR_NAME
    return Path.home() / "." + DATA_DIR_NAME.lower()


def db_path() -> Path:
    return app_data_dir() / "index.db"


def icon_path() -> Path:
    # 可执行文件打包后图标随程序目录发布
    exe_dir = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent.parent))
    return exe_dir / "assets" / "icon.ico"


def asset_path(name: str) -> Path:
    exe_dir = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent.parent))
    return exe_dir / "assets" / name
