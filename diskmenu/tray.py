"""PySide6 系统托盘（QSystemTrayIcon）与 USB 设备事件监听。"""

from __future__ import annotations

import ctypes
import threading
from ctypes import wintypes
from datetime import datetime
from typing import Callable, Optional

from PySide6.QtCore import QAbstractNativeEventFilter, QObject, Qt, Signal
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QApplication, QFileDialog, QMenu, QSystemTrayIcon, QWidget

from . import db, exporter
from .paths import APP_TITLE, icon_path
from .qt_theme import apply_theme
from .util import safe_filename
from .volumes import is_eligible, list_volumes, mounted_drive

WM_DEVICECHANGE = 0x0219
DBT_DEVICEARRIVAL = 0x8000
DBT_DEVICEREMOVECOMPLETE = 0x8004
DBT_DEVTYP_DEVICEINTERFACE = 0x0005
DEVICE_NOTIFY_WINDOW_HANDLE = 0x0000

user32 = ctypes.windll.user32


class GUID(ctypes.Structure):
    _fields_ = [
        ("Data1", wintypes.DWORD),
        ("Data2", wintypes.WORD),
        ("Data3", wintypes.WORD),
        ("Data4", ctypes.c_ubyte * 8),
    ]


GUID_DEVINTERFACE_VOLUME = GUID(
    0x53F5630D,
    0xB6BF,
    0x11D0,
    (ctypes.c_ubyte * 8)(0x94, 0xF2, 0x00, 0xA0, 0xC9, 0x1E, 0xFB, 0x8B),
)


class DEV_BROADCAST_HDR(ctypes.Structure):
    _fields_ = [
        ("dbch_size", wintypes.DWORD),
        ("dbch_devicetype", wintypes.DWORD),
        ("dbch_reserved", wintypes.DWORD),
    ]


class DEV_BROADCAST_DEVICEINTERFACE_W(ctypes.Structure):
    _fields_ = [
        ("dbcc_size", wintypes.DWORD),
        ("dbcc_devicetype", wintypes.DWORD),
        ("dbcc_reserved", wintypes.DWORD),
        ("dbcc_classguid", GUID),
        ("dbcc_name", wintypes.WCHAR * 1),
    ]


class MSG(ctypes.Structure):
    _fields_ = [
        ("hwnd", wintypes.HWND),
        ("message", wintypes.UINT),
        ("wParam", wintypes.WPARAM),
        ("lParam", wintypes.LPARAM),
        ("time", wintypes.DWORD),
        ("pt", wintypes.POINT),
    ]


user32.RegisterDeviceNotificationW.restype = wintypes.HANDLE
user32.RegisterDeviceNotificationW.argtypes = [
    wintypes.HANDLE,
    wintypes.LPVOID,
    wintypes.DWORD,
]
user32.UnregisterDeviceNotification.restype = wintypes.BOOL
user32.UnregisterDeviceNotification.argtypes = [wintypes.HANDLE]


class _DeviceChangeFilter(QAbstractNativeEventFilter):
    """捕获 WM_DEVICECHANGE 广播，立即唤醒后台服务。"""

    def __init__(self, callback: Callable[[], None]) -> None:
        super().__init__()
        self._callback = callback

    def nativeEventFilter(self, eventType, message):
        try:
            et = bytes(eventType)
        except Exception:
            et = str(eventType).encode("utf-8")
        if et == b"windows_generic_MSG":
            try:
                msg = ctypes.cast(int(message), ctypes.POINTER(MSG)).contents
                if msg.message == WM_DEVICECHANGE and msg.wParam in (
                    DBT_DEVICEARRIVAL,
                    DBT_DEVICEREMOVECOMPLETE,
                ):
                    try:
                        self._callback()
                    except Exception:
                        pass
            except Exception:
                pass
        return False, 0


class _DeviceWatcher(QWidget):
    """隐藏窗口：注册设备通知，使 WM_DEVICECHANGE 能送达事件循环。"""

    def __init__(self) -> None:
        super().__init__(None, Qt.Tool)
        self.setWindowTitle("DiskMenuDeviceWatcher")
        self._reg_handle = None

    def start(self) -> None:
        self.setAttribute(Qt.WA_DontShowOnScreen, True)
        self.winId()  # 强制创建原生窗口
        dbi = DEV_BROADCAST_DEVICEINTERFACE_W()
        dbi.dbcc_size = ctypes.sizeof(DEV_BROADCAST_DEVICEINTERFACE_W)
        dbi.dbcc_devicetype = DBT_DEVTYP_DEVICEINTERFACE
        dbi.dbcc_reserved = 0
        dbi.dbcc_classguid = GUID_DEVINTERFACE_VOLUME
        self._reg_handle = user32.RegisterDeviceNotificationW(
            int(self.winId()),
            ctypes.byref(dbi),
            DEVICE_NOTIFY_WINDOW_HANDLE,
        )

    def stop(self) -> None:
        if self._reg_handle:
            try:
                user32.UnregisterDeviceNotification(self._reg_handle)
            except Exception:
                pass
            self._reg_handle = None


class TrayIcon(QObject):
    """系统托盘图标（QSystemTrayIcon）。"""

    notify_requested = Signal(str, str)

    def __init__(
        self,
        title: str = APP_TITLE,
        on_open: Optional[Callable[[], None]] = None,
        on_quit: Optional[Callable[[], None]] = None,
        on_device_change: Optional[Callable[[], None]] = None,
        db_path: Optional[str] = None,
    ) -> None:
        super().__init__()
        self.title = title
        self.on_open = on_open
        self.on_quit = on_quit
        self._on_device_change = on_device_change
        self._db_path = db_path
        self._tray: Optional[QSystemTrayIcon] = None
        self._menu: Optional[QMenu] = None
        self._scan_action = None
        self._watcher: Optional[_DeviceWatcher] = None
        self._filter: Optional[_DeviceChangeFilter] = None
        self._thread: Optional[threading.Thread] = None  # 兼容旧调用方

    # ---------------- 生命周期 ----------------

    def start(self) -> None:
        app = QApplication.instance() or QApplication([])
        apply_theme(app, "light")
        app.setQuitOnLastWindowClosed(False)
        self.notify_requested.connect(self._show_message)

        tray = QSystemTrayIcon(QIcon(str(icon_path())), app)
        tray.setToolTip(self.title)
        menu = QMenu()
        open_action = menu.addAction("打开主界面")
        open_action.triggered.connect(self._on_open)
        menu.addSeparator()
        self._scan_action = menu.addAction("开始扫描")
        self._scan_action.triggered.connect(self._toggle_scan)
        export_action = menu.addAction("导出报告")
        export_action.triggered.connect(self._export_all)
        menu.addSeparator()
        quit_action = menu.addAction("退出")
        quit_action.triggered.connect(self._quit)
        menu.aboutToShow.connect(self._update_menu)
        tray.setContextMenu(menu)
        tray.activated.connect(self._on_activated)
        tray.show()
        self._tray = tray
        self._menu = menu

        self._filter = _DeviceChangeFilter(self._on_device_change_event)
        app.installNativeEventFilter(self._filter)
        self._watcher = _DeviceWatcher()
        self._watcher.start()

        app.exec()

        # 事件循环退出后的清理
        if self._filter is not None:
            try:
                app.removeNativeEventFilter(self._filter)
            except Exception:
                pass
            self._filter = None
        if self._watcher is not None:
            self._watcher.stop()
            self._watcher = None
        if self._tray is not None:
            self._tray.hide()
            self._tray = None

    def stop(self) -> None:
        if self._tray is not None:
            try:
                self._tray.hide()
            except Exception:
                pass
        app = QApplication.instance()
        if app is not None:
            app.quit()

    def wait(self) -> None:
        """兼容入口：Qt 事件循环在 start() 内阻塞运行，无需额外等待。"""

    def notify(self, title: str, message: str) -> None:
        """显示托盘气泡通知（线程安全）。"""
        self.notify_requested.emit(title, message)

    def _show_message(self, title: str, message: str) -> None:
        if self._tray is not None:
            self._tray.showMessage(title, message, QSystemTrayIcon.Information, 5000)

    # ---------------- 事件 ----------------

    def _on_activated(self, reason) -> None:
        if reason == QSystemTrayIcon.DoubleClick:
            self._on_open()

    def _on_open(self) -> None:
        if self.on_open:
            try:
                self.on_open()
            except Exception:
                pass

    def _on_device_change_event(self) -> None:
        if self._on_device_change:
            try:
                self._on_device_change()
            except Exception:
                pass

    def _quit(self) -> None:
        if self.on_quit:
            try:
                self.on_quit()
            except Exception:
                pass

    # ---------------- 菜单动作 ----------------

    def _update_menu(self) -> None:
        if self._scan_action is not None:
            self._scan_action.setText("停止扫描" if self._scan_active() else "开始扫描")

    def _scan_active(self) -> bool:
        conn = db.connect(self._db_path)
        try:
            db.init_db(conn)
            return any(r["status"] in ("scanning", "queued") for r in db.list_disks(conn))
        finally:
            conn.close()

    def _toggle_scan(self) -> None:
        if self._scan_active():
            conn = db.connect(self._db_path)
            try:
                db.init_db(conn)
                for req in conn.execute("SELECT id FROM scan_requests WHERE status='queued'").fetchall():
                    db.finish_scan_request(conn, req["id"], False, "用户取消")
            finally:
                conn.close()
            self.notify(APP_TITLE, "已取消排队中的扫描任务")
            return

        conn = db.connect(self._db_path)
        try:
            db.init_db(conn)
            settings = db.get_settings(conn)
            app_drive = mounted_drive()
            count = 0
            for vol in list_volumes():
                if is_eligible(vol, settings, app_drive):
                    if db.request_scan(conn, vol.disk_id, "incremental"):
                        count += 1
        finally:
            conn.close()
        if count:
            self._on_device_change_event()  # 唤醒服务立即处理队列
        self.notify(APP_TITLE, f"已加入 {count} 块硬盘的增量扫描队列" if count else "没有可扫描的硬盘")

    def _export_all(self) -> None:
        conn = db.connect(self._db_path)
        try:
            db.init_db(conn)
            disks = [r for r in db.list_disks(conn) if r["status"] == "completed" and r["total_files"]]
        finally:
            conn.close()
        if not disks:
            self.notify(APP_TITLE, "没有可导出的索引（需要先完成扫描）")
            return
        if len(disks) == 1:
            disk = disks[0]
            serial = disk["volume_serial"] or ""
            base = safe_filename(disk["label"].strip() or f"{disk['drive_letter'].replace(':', '')}_{serial}")
            default = f"DiskMenu_{base}_{datetime.now():%Y%m%d_%H%M}.html"
            path, _ = QFileDialog.getSaveFileName(
                None,
                "导出为 HTML 离线报告",
                default,
                "HTML 文件 (*.html)",
            )
            if not path:
                return
            self._run_export([(disk, path)])
            return
        folder = QFileDialog.getExistingDirectory(None, "选择导出文件夹")
        if not folder:
            return
        jobs = []
        for disk in disks:
            serial = disk["volume_serial"] or ""
            base = safe_filename(disk["label"].strip() or f"{disk['drive_letter'].replace(':', '')}_{serial}")
            out = f"{folder}\\{base}_{datetime.now():%Y%m%d_%H%M%S}.html"
            jobs.append((disk, out))
        self._run_export(jobs)

    def _run_export(self, jobs: list) -> None:
        threading.Thread(target=self._export_worker, args=(jobs,), daemon=True).start()

    def _export_worker(self, jobs: list) -> None:
        ok_count = 0
        for disk, out in jobs:
            try:
                ok, _msg = exporter.export_html(self._db_path, disk["disk_id"], out)
                if ok:
                    ok_count += 1
            except Exception:
                pass
        self.notify_requested.emit(APP_TITLE, f"导出完成：{ok_count}/{len(jobs)}")
