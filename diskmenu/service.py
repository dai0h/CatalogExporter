"""后台服务：轮询卷变化、自动入队扫描、维护索引状态。"""

from __future__ import annotations

import threading
import time
from datetime import datetime
from pathlib import Path
from typing import Callable, Optional

from . import db, scanner
from .exporter import export_html
from .paths import app_data_dir
from .util import safe_filename
from .volumes import VolumeInfo, drive_is_usb, invalidate_external_cache, is_eligible, list_volumes, mounted_drive


class DiskMenuService:
    def __init__(
        self,
        db_path: Optional[str] = None,
        notify: Optional[Callable[[str, str], None]] = None,
    ) -> None:
        self.db_path = db_path
        self.notify = notify
        self._stop = threading.Event()
        self._threads: list[threading.Thread] = []
        self._known_mounted: dict[str, VolumeInfo] = {}
        self._removed_since: set[str] = set()
        self._retry_at: dict[str, float] = {}
        self._boot_export_done = False

    def start(self) -> None:
        conn = db.connect(self.db_path)
        try:
            db.init_db(conn)
        finally:
            conn.close()
        self._refresh_volumes(initial=True)
        self._threads.append(threading.Thread(target=self._poller_loop, name="DiskMenu-poller", daemon=True))
        self._threads.append(threading.Thread(target=self._worker_loop, name="DiskMenu-scanner", daemon=True))
        for t in self._threads:
            t.start()

    def stop(self) -> None:
        self._stop.set()
        for t in self._threads:
            t.join(timeout=3)
        self._threads.clear()

    def wake(self) -> None:
        """设备插入/拔出事件触发，立即重新枚举卷。"""
        invalidate_external_cache()
        self._refresh_volumes(initial=False)

    # ---------------- volume watching ----------------

    def _poller_loop(self) -> None:
        while not self._stop.is_set():
            try:
                self._refresh_volumes(initial=False)
            except Exception:
                pass
            self._stop.wait(3)

    def _refresh_volumes(self, initial: bool = False) -> None:
        conn = db.connect(self.db_path)
        try:
            db.init_db(conn)
            settings = db.get_settings(conn)
            app_drive = mounted_drive()
            current: dict[str, VolumeInfo] = {}

            for vol in list_volumes():
                if not is_eligible(vol, settings, app_drive):
                    continue
                current[vol.disk_id] = vol
                created = db.ensure_disk(
                    conn,
                    vol.disk_id,
                    label=vol.label,
                    drive_letter=vol.drive,
                    volume_serial=vol.serial,
                    file_system=vol.file_system,
                    volume_size=vol.total,
                    volume_free=vol.free,
                )
                row = db.get_disk(conn, vol.disk_id)
                assert row is not None
                prev = self._known_mounted.get(vol.disk_id)

                needs_scan = False
                if initial:
                    needs_scan = (
                        created
                        or row["status"] in ("none", "partial", "error", "queued")
                        or row["last_scan_finished"] is None
                    )
                else:
                    if prev is None or prev.drive != vol.drive:
                        needs_scan = True
                    elif vol.disk_id in self._removed_since:
                        needs_scan = True
                    elif row["status"] in ("none", "partial", "error", "queued"):
                        needs_scan = True

                if needs_scan:
                    db.request_scan(conn, vol.disk_id, "incremental")
                self._removed_since.discard(vol.disk_id)

            # 不在线的卷标记为 removed，但保留索引
            for row in db.list_disks(conn):
                if row["disk_id"] not in current:
                    self._removed_since.add(row["disk_id"])
                    if row["status"] not in ("scanning", "queued"):
                        db.set_disk_status(conn, row["disk_id"], "removed", "硬盘未连接")
                    self._known_mounted.pop(row["disk_id"], None)

            self._known_mounted = current
        finally:
            conn.close()

    # ---------------- scan worker ----------------

    def _worker_loop(self) -> None:
        while not self._stop.is_set():
            conn = db.connect(self.db_path)
            req_id = None
            try:
                db.init_db(conn)
                if not self._boot_export_done:
                    self._export_all_on_boot(conn)
                    self._boot_export_done = True
                    continue
                req = db.take_scan_request(conn)
                if req is None:
                    # 补扫：部分完成/出错的盘若已挂载，自动重新入队
                    for row in db.list_disks(conn):
                        if row["status"] in ("none", "partial", "error") and row["drive_letter"]:
                            if time.time() >= self._retry_at.get(row["disk_id"], 0):
                                if db.request_scan(conn, row["disk_id"], "incremental"):
                                    self._retry_at[row["disk_id"]] = time.time() + 30
                    self._stop.wait(0.5)
                    continue

                req_id = req["id"]
                disk = db.get_disk(conn, req["disk_id"])
                if disk is None:
                    db.finish_scan_request(conn, req["id"], False, "硬盘记录不存在")
                    continue
                if not disk["drive_letter"]:
                    db.finish_scan_request(conn, req["id"], False, "硬盘未连接")
                    continue

                ok, message = scanner.scan_disk(
                    req["disk_id"],
                    mode=req["mode"],
                    db_path=self.db_path,
                    stop_event=self._stop,
                )
                export_path = None
                if ok:
                    export_path = self._auto_export(conn, req["disk_id"], "insert")
                db.finish_scan_request(conn, req["id"], ok, message)
                if self.notify:
                    title = "索引完成" if ok else "索引暂停"
                    name = disk["label"].strip() or disk["drive_letter"] or "硬盘"
                    text = f"{name}: {message}"
                    if export_path:
                        text += f"\n已自动导出：{export_path}"
                    self.notify(title, text)
            except Exception as exc:
                try:
                    if req_id is not None:
                        db.finish_scan_request(conn, req_id, False, str(exc))
                except Exception:
                    pass
            finally:
                conn.close()
            self._stop.wait(0.5)

    # ---------------- auto export ----------------

    def _export_all_on_boot(self, conn) -> None:
        settings = db.get_settings(conn)
        if settings.get("auto_export_on_boot", "0") != "1":
            return
        for row in db.list_disks(conn):
            if row["status"] == "completed" and row["total_files"]:
                self._auto_export(conn, row["disk_id"], "boot")

    def _auto_export(self, conn, disk_id: str, trigger: str) -> Optional[str]:
        settings = db.get_settings(conn)
        key = "auto_export_on_boot" if trigger == "boot" else "auto_export_on_insert"
        if settings.get(key, "0") != "1":
            return None
        export_dir = settings.get("auto_export_dir", "").strip()
        if not export_dir:
            return None
        disk = db.get_disk(conn, disk_id)
        if disk is None or not disk["total_files"]:
            return None
        try:
            out_dir = Path(export_dir)
            out_dir.mkdir(parents=True, exist_ok=True)
            drive_part = (disk["drive_letter"] or "").replace(":", "").lower() or "disk"
            serial = (disk["volume_serial"] or "").lower()
            if not serial:
                serial = disk["disk_id"].split("{")[-1].rstrip("}").split("-")[0][:8].lower() or "disk"
            usb = drive_is_usb(disk["drive_letter"] or "")
            usb_text = "_usb" if usb else ""
            drive_folder = safe_filename(f"{drive_part}盘{usb_text}_{serial}")
            disk_out_dir = out_dir / drive_folder
            disk_out_dir.mkdir(parents=True, exist_ok=True)
            base = safe_filename((disk["label"].strip() or f"{drive_part}盘{usb_text}") + "_" + serial)
            out = disk_out_dir / f"{base}_{datetime.now():%Y%m%d_%H%M%S}.html"
            ok, msg = export_html(self.db_path, disk_id, out)
            if not ok:
                self._log(f"自动导出失败：{msg}")
                return None
            return str(out)
        except Exception as exc:
            self._log(f"自动导出异常：{exc}")
            return None

    def _log(self, text: str) -> None:
        try:
            log_path = app_data_dir() / "error.log"
            log_path.parent.mkdir(parents=True, exist_ok=True)
            with open(log_path, "a", encoding="utf-8") as f:
                f.write(text + "\n")
        except Exception:
            pass
