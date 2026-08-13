"""开机自启：写入/删除 HKCU Run 注册表项。"""

from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Optional

import winreg

RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
VALUE_NAME = "CatalogExporter"
OLD_VALUE_NAME = "DiskMenu"
STARTUP_FILE = "CatalogExporter.vbs"
OLD_STARTUP_FILE = "CatalogExporter.cmd"


def startup_folder() -> Path:
    appdata = os.environ.get("APPDATA") or str(Path.home())
    return Path(appdata) / "Microsoft" / "Windows" / "Start Menu" / "Programs" / "Startup"


def tray_command() -> str:
    if getattr(sys, "frozen", False):
        return f'"{sys.executable}" --autostart'
    python = Path(sys.executable)
    pythonw = python.with_name("pythonw.exe")
    exe = pythonw if pythonw.exists() else python
    script = Path(__file__).resolve().parent.parent / "run_tray.pyw"
    return f'"{exe}" "{script}"'


def install(command: Optional[str] = None) -> None:
    cmd = command or tray_command()
    try:
        with winreg.CreateKeyEx(winreg.HKEY_CURRENT_USER, RUN_KEY, 0, winreg.KEY_SET_VALUE) as key:
            winreg.SetValueEx(key, VALUE_NAME, 0, winreg.REG_SZ, cmd)
            try:
                winreg.DeleteValue(key, OLD_VALUE_NAME)
            except FileNotFoundError:
                pass
    except OSError:
        pass
    # 只保留注册表启动项，移除 Start Menu 里的脚本，避免重复启动项和安全软件提示
    try:
        (startup_folder() / STARTUP_FILE).unlink(missing_ok=True)
        (startup_folder() / OLD_STARTUP_FILE).unlink(missing_ok=True)
    except OSError:
        pass


def uninstall() -> None:
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY, 0, winreg.KEY_SET_VALUE) as key:
            winreg.DeleteValue(key, VALUE_NAME)
            try:
                winreg.DeleteValue(key, OLD_VALUE_NAME)
            except FileNotFoundError:
                pass
    except FileNotFoundError:
        pass
    try:
        (startup_folder() / STARTUP_FILE).unlink(missing_ok=True)
        (startup_folder() / OLD_STARTUP_FILE).unlink(missing_ok=True)
    except OSError:
        pass


def is_installed() -> bool:
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY, 0, winreg.KEY_QUERY_VALUE) as key:
            winreg.QueryValueEx(key, VALUE_NAME)
        return True
    except FileNotFoundError:
        pass
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY, 0, winreg.KEY_QUERY_VALUE) as key:
            winreg.QueryValueEx(key, VALUE_NAME)
        return True
    except FileNotFoundError:
        return False
