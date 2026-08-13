"""扫描器：只读遍历卷目录，写入 SQLite；支持增量、断点续扫、安全中止。"""

from __future__ import annotations

import os
import time
from typing import Callable, Iterable, Optional

from . import db

FILE_ATTRIBUTE_HIDDEN = 0x2
FILE_ATTRIBUTE_SYSTEM = 0x4
FILE_ATTRIBUTE_REPARSE_POINT = 0x400
FILE_ATTRIBUTE_DIRECTORY = 0x10


def _rel_path(root_abs: str, abs_path: str) -> str:
    rel = os.path.relpath(abs_path, root_abs)
    if rel == ".":
        return ""
    return rel.replace("\\", "/")


def _entry_info(root_abs: str, entry: os.DirEntry, st=None):
    """返回 (rel_path, name, parent, is_dir, size, mtime, ext, hidden, system)。"""
    if st is None:
        st = entry.stat(follow_symlinks=False)
    attrs = getattr(st, "st_file_attributes", 0)
    hidden = bool(attrs & FILE_ATTRIBUTE_HIDDEN)
    system = bool(attrs & FILE_ATTRIBUTE_SYSTEM)
    is_dir = bool(attrs & FILE_ATTRIBUTE_DIRECTORY) or entry.is_dir(follow_symlinks=False)
    rel = _rel_path(root_abs, entry.path)
    parent = rel.rsplit("/", 1)[0] if "/" in rel else ""
    size = int(st.st_size or 0)
    mtime = int(st.st_mtime or 0)
    ext = ""
    if not is_dir:
        ext = os.path.splitext(entry.name)[1].lower().lstrip(".")
    return rel, entry.name, parent, int(is_dir), size, mtime, ext, int(hidden), int(system)


def _drive_missing(drive_root: str) -> bool:
    try:
        return not os.path.exists(drive_root)
    except OSError:
        return True


def scan_disk(
    disk_id: str,
    mode: str = "incremental",
    db_path: Optional[str] = None,
    on_progress: Optional[Callable[[dict], None]] = None,
    stop_event=None,
) -> tuple[bool, str]:
    """扫描一块已挂载的卷。mode: incremental|full。返回 (是否成功, 消息)。"""
    pid = os.getpid()
    conn = db.connect(db_path)
    try:
        disk = db.get_disk(conn, disk_id)
        if disk is None:
            return False, "未找到该硬盘的索引记录"
        drive = (disk["drive_letter"] or "").strip()
        if not drive:
            return False, "硬盘当前未连接"
        drive_root = drive.rstrip("\\") + "\\"

        if not db.try_acquire_scan_lock(conn, pid):
            return False, "已有扫描任务正在进行"

        settings = db.get_settings(conn)
        scan_hidden = settings.get("scan_hidden", "0") == "1"
        scan_system = settings.get("scan_system", "0") == "1"
        force = mode == "full"

        old_total = db.count_files(conn, disk_id)
        job_id, resumed = db.create_or_resume_job(conn, disk_id, force=force)
        if not resumed:
            db.enqueue_dirs(conn, job_id, [""])

        db.set_disk_scan_start(conn, disk_id)
        started = db.now()
        processed = 0
        errors = 0
        skipped = 0
        seen_count = 0
        aborted = False
        abort_reason = ""

        while True:
            if stop_event is not None and stop_event.is_set():
                aborted = True
                abort_reason = "用户中止"
                break
            if _drive_missing(drive_root):
                aborted = True
                abort_reason = "硬盘已拔出，扫描暂停"
                break

            item = db.peek_next_dir(conn, job_id)
            if item is None:
                break
            seq = item["seq"]
            rel_dir = item["dir_path"]
            abs_dir = drive_root if rel_dir == "" else os.path.join(drive_root, rel_dir.replace("/", "\\"))

            try:
                it = os.scandir(abs_dir)
            except FileNotFoundError:
                if _drive_missing(drive_root):
                    aborted = True
                    abort_reason = "硬盘已拔出，扫描暂停"
                    break
                errors += 1
                db.finish_dir(conn, job_id, seq, rel_dir, [], [])
                continue
            except PermissionError:
                errors += 1
                db.finish_dir(conn, job_id, seq, rel_dir, [], [])
                continue
            except OSError as exc:
                if _drive_missing(drive_root):
                    aborted = True
                    abort_reason = "硬盘已拔出，扫描暂停"
                    break
                errors += 1
                db.finish_dir(conn, job_id, seq, rel_dir, [], [])
                continue

            batch = []
            subdirs = []
            with it:
                while True:
                    try:
                        entry = next(it)
                    except StopIteration:
                        break
                    except (OSError, UnicodeError, ValueError):
                        errors += 1
                        continue
                    try:
                        if entry.is_symlink():
                            skipped += 1
                            continue
                        st = entry.stat(follow_symlinks=False)
                        if getattr(st, "st_file_attributes", 0) & FILE_ATTRIBUTE_REPARSE_POINT:
                            skipped += 1
                            continue
                        rel, name, parent, is_dir, size, mtime, ext, hidden, system = _entry_info(drive_root, entry, st)
                        if (hidden and not scan_hidden) or (system and not scan_system):
                            skipped += 1
                            continue
                        batch.append((rel, name, parent, is_dir, size, mtime, ext, hidden, system))
                        if is_dir:
                            subdirs.append(rel)
                    except (OSError, UnicodeError, ValueError):
                        errors += 1

            db.finish_dir(conn, job_id, seq, rel_dir, subdirs, batch)
            processed += 1
            seen_count += len(batch)
            db.touch_job(conn, job_id, processed, errors, skipped, rel_dir)
            db.set_disk_scan_progress(conn, disk_id, processed, errors, skipped, rel_dir)
            if processed % 10 == 0:
                db.heartbeat_scan_lock(conn, pid)
            if on_progress:
                on_progress(
                    {
                        "disk_id": disk_id,
                        "current": rel_dir,
                        "processed": processed,
                        "errors": errors,
                        "skipped": skipped,
                        "seen": seen_count,
                    }
                )

        if aborted:
            db.abort_job(conn, job_id, abort_reason)
            db.abort_disk_scan(conn, disk_id, abort_reason)
            db.insert_scan_log(
                conn, disk_id, job_id, mode, started, db.now(), seen_count, 0, 0, 0,
                errors, skipped, aborted=1, message=abort_reason,
            )
            return False, abort_reason

        # 正常完成：删除本次未看到的历史条目
        deleted = db.delete_unseen(conn, disk_id, job_id)
        new_total = db.count_files(conn, disk_id)
        new_size = db.count_size(conn, disk_id)
        new_files = conn.execute(
            "SELECT COUNT(*) AS c FROM files WHERE disk_id=? AND is_dir=0",
            (disk_id,),
        ).fetchone()["c"]
        added = max(0, new_total - (old_total - deleted))
        changed = added + deleted
        db.finish_disk_scan(
            conn, disk_id, new_files, new_size, added, deleted, changed, errors, skipped, "完成",
        )
        db.finish_job(conn, job_id, "完成")
        db.insert_scan_log(
            conn, disk_id, job_id, mode, started, db.now(), seen_count, added, deleted, changed,
            errors, skipped, aborted=0, message="完成",
        )
        return True, "索引完成"
    except Exception as exc:
        try:
            if "job_id" in locals() and "started" in locals():
                message = f"扫描出错：{exc}"
                db.abort_job(conn, job_id, message)
                db.abort_disk_scan(conn, disk_id, message)
                db.insert_scan_log(
                    conn, disk_id, job_id, mode, started, db.now(), 0, 0, 0, 0,
                    0, 0, aborted=1, message=message,
                )
        except Exception:
            pass
        return False, f"扫描出错：{exc}"
    finally:
        try:
            db.release_scan_lock(conn, pid)
        except Exception:
            pass
        conn.close()
