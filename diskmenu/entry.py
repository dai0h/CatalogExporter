"""进程入口：托盘服务 / 图形界面。"""

from __future__ import annotations

import os
import subprocess
import sys
from typing import Optional

from . import autostart
from .paths import APP_TITLE
from .service import DiskMenuService
from .single_instance import SingleInstance


def _run_tray_command() -> list[str]:
    if getattr(sys, "frozen", False):
        return [sys.executable, "--autostart"]
    python = sys.executable
    pythonw = os.path.join(os.path.dirname(python), "pythonw.exe")
    if os.path.exists(pythonw):
        python = pythonw
    script = os.path.join(os.path.dirname(os.path.dirname(__file__)), "run_tray.pyw")
    return [python, script]


def ensure_tray_running() -> None:
    if SingleInstance.is_running("CatalogExporterV2Tray"):
        return
    try:
        creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0) | getattr(subprocess, "DETACHED_PROCESS", 0)
        subprocess.Popen(
            _run_tray_command(),
            creationflags=creationflags,
            close_fds=True,
        )
    except Exception:
        pass


def start_tray(db_path: Optional[str] = None) -> None:
    instance = SingleInstance("CatalogExporterV2Tray")
    if not instance.acquire():
        return  # 已有托盘实例

    service = None
    tray = None

    try:
        from .tray import TrayIcon

        def open_gui():
            ensure_gui_process()

        def quit_app():
            if service:
                service.stop()
            if tray:
                tray.stop()
            instance.release()

        service = DiskMenuService(db_path=db_path)
        service.start()
        tray = TrayIcon(title=APP_TITLE, on_open=open_gui, on_quit=quit_app, on_device_change=service.wake)
        tray.start()
        # 托盘消息循环由独立线程运行；主线程等待退出事件
        tray._thread.join()
    except KeyboardInterrupt:
        pass
    finally:
        if service:
            service.stop()
        if tray:
            tray.stop()
        instance.release()


def ensure_gui_process() -> None:
    if getattr(sys, "frozen", False):
        subprocess.Popen([sys.executable, "gui"])
        return
    python = sys.executable
    pythonw = os.path.join(os.path.dirname(python), "pythonw.exe")
    if os.path.exists(pythonw):
        python = pythonw
    script = os.path.join(os.path.dirname(os.path.dirname(__file__)), "run_gui.pyw")
    subprocess.Popen([python, script])


def start_gui(db_path: Optional[str] = None) -> None:
    ensure_tray_running()
    from .gui import run

    run(db_path)
