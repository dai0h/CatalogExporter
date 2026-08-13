"""SQLite 数据层：索引、扫描任务、设置、请求。"""

from __future__ import annotations

import sqlite3
import time
from pathlib import Path
from typing import Any, Iterable, Optional

from .paths import db_path as default_db_path

SCHEMA = """
CREATE TABLE IF NOT EXISTS disks (
    disk_id            TEXT PRIMARY KEY,
    label              TEXT DEFAULT '',
    drive_letter       TEXT DEFAULT '',
    volume_serial      TEXT DEFAULT '',
    file_system        TEXT DEFAULT '',
    volume_size        INTEGER DEFAULT 0,
    volume_free        INTEGER DEFAULT 0,
    status             TEXT DEFAULT 'none',      -- none|queued|scanning|partial|completed|error|removed
    scan_current       TEXT DEFAULT '',
    scan_processed     INTEGER DEFAULT 0,
    scan_errors        INTEGER DEFAULT 0,
    scan_skipped       INTEGER DEFAULT 0,
    last_scan_started  INTEGER,
    last_scan_finished INTEGER,
    total_files        INTEGER DEFAULT 0,
    total_size         INTEGER DEFAULT 0,
    last_added         INTEGER DEFAULT 0,
    last_deleted       INTEGER DEFAULT 0,
    last_changed       INTEGER DEFAULT 0,
    last_error         TEXT DEFAULT '',
    updated_at         INTEGER
);

CREATE TABLE IF NOT EXISTS files (
    disk_id      TEXT NOT NULL,
    path         TEXT NOT NULL,          -- 相对路径，/ 分隔；根目录为 ''
    name         TEXT NOT NULL,
    parent       TEXT NOT NULL,          -- 父目录相对路径；根目录下为 ''
    is_dir       INTEGER NOT NULL DEFAULT 0,
    size         INTEGER NOT NULL DEFAULT 0,
    mtime        INTEGER NOT NULL DEFAULT 0,
    ext          TEXT DEFAULT '',
    hidden       INTEGER NOT NULL DEFAULT 0,
    system       INTEGER NOT NULL DEFAULT 0,
    seen_session INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (disk_id, path)
) WITHOUT ROWID;

CREATE INDEX IF NOT EXISTS idx_files_disk_parent ON files(disk_id, parent);
CREATE INDEX IF NOT EXISTS idx_files_disk_name   ON files(disk_id, name);
CREATE INDEX IF NOT EXISTS idx_files_disk_ext    ON files(disk_id, ext);
CREATE INDEX IF NOT EXISTS idx_files_seen        ON files(disk_id, seen_session);

CREATE TABLE IF NOT EXISTS scan_jobs (
    job_id       INTEGER PRIMARY KEY AUTOINCREMENT,
    disk_id      TEXT NOT NULL,
    status       TEXT NOT NULL DEFAULT 'pending', -- pending|running|completed|aborted
    mode         TEXT NOT NULL DEFAULT 'incremental',
    started_at   INTEGER,
    finished_at  INTEGER,
    updated_at   INTEGER,
    current_path TEXT DEFAULT '',
    processed    INTEGER DEFAULT 0,
    errors       INTEGER DEFAULT 0,
    skipped      INTEGER DEFAULT 0,
    message      TEXT DEFAULT ''
);

CREATE TABLE IF NOT EXISTS scan_queue (
    job_id   INTEGER NOT NULL,
    seq      INTEGER NOT NULL,
    dir_path TEXT NOT NULL,
    PRIMARY KEY (job_id, seq)
);

CREATE TABLE IF NOT EXISTS scan_log (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    disk_id     TEXT NOT NULL,
    job_id      INTEGER,
    mode        TEXT DEFAULT 'incremental',
    started_at  INTEGER,
    finished_at INTEGER,
    total_found INTEGER DEFAULT 0,
    added       INTEGER DEFAULT 0,
    deleted     INTEGER DEFAULT 0,
    changed     INTEGER DEFAULT 0,
    errors      INTEGER DEFAULT 0,
    skipped     INTEGER DEFAULT 0,
    aborted     INTEGER DEFAULT 0,
    message     TEXT DEFAULT ''
);

CREATE TABLE IF NOT EXISTS scan_requests (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    disk_id      TEXT NOT NULL,
    mode         TEXT DEFAULT 'incremental',
    requested_at INTEGER,
    status       TEXT DEFAULT 'queued', -- queued|running|done|failed
    message      TEXT DEFAULT ''
);

CREATE TABLE IF NOT EXISTS scan_lock (
    id             INTEGER PRIMARY KEY CHECK (id = 1),
    pid            INTEGER,
    started_at     INTEGER,
    last_heartbeat INTEGER
);

CREATE TABLE IF NOT EXISTS meta (
    key   TEXT PRIMARY KEY,
    value TEXT
);
"""


def connect(db_path: Optional[Path | str] = None) -> sqlite3.Connection:
    path = Path(db_path) if db_path else default_db_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path), timeout=30, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    conn.execute("PRAGMA foreign_keys=ON")
    conn.execute("PRAGMA busy_timeout=30000")
    return conn


def init_db(conn: sqlite3.Connection) -> None:
    conn.executescript(SCHEMA)
    cols = {row["name"] for row in conn.execute("PRAGMA table_info(disks)")}
    if "volume_free" not in cols:
        conn.execute("ALTER TABLE disks ADD COLUMN volume_free INTEGER DEFAULT 0")
    conn.commit()


def now() -> int:
    return int(time.time())


# ---------------- settings ----------------

DEFAULTS = {
    "start_at_login": "0",
    "scan_hidden": "0",
    "scan_system": "0",
    "scan_removable": "1",
    "scan_fixed_new": "1",
    "ignore_drives": "",
    "extra_external": "",
    "password_hash": "",
    "last_export_dir": "",
    "auto_export_on_boot": "0",
    "auto_export_on_insert": "0",
    "auto_export_dir": "",
}


def get_settings(conn: sqlite3.Connection) -> dict[str, str]:
    rows = conn.execute("SELECT key, value FROM meta").fetchall()
    data = dict(DEFAULTS)
    for row in rows:
        data[row["key"]] = row["value"]
    return data


def set_setting(conn: sqlite3.Connection, key: str, value: str) -> None:
    conn.execute(
        "INSERT INTO meta(key, value) VALUES(?, ?) "
        "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
        (key, str(value)),
    )
    conn.commit()


def set_settings_many(conn: sqlite3.Connection, values: dict[str, str]) -> None:
    for key, value in values.items():
        conn.execute(
            "INSERT INTO meta(key, value) VALUES(?, ?) "
            "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
            (key, str(value)),
        )
    conn.commit()


# ---------------- disks ----------------


def ensure_disk(
    conn: sqlite3.Connection,
    disk_id: str,
    label: str = "",
    drive_letter: str = "",
    volume_serial: str = "",
    file_system: str = "",
    volume_size: int = 0,
    volume_free: int = 0,
) -> bool:
    """登记一块卷；返回 True 表示新建。"""
    existing = conn.execute("SELECT 1 FROM disks WHERE disk_id=?", (disk_id,)).fetchone()
    created = existing is None
    if created:
        conn.execute(
            "INSERT INTO disks(disk_id, label, drive_letter, volume_serial, file_system, volume_size, volume_free, updated_at) "
            "VALUES(?,?,?,?,?,?,?,?)",
            (disk_id, label, drive_letter, volume_serial, file_system, volume_size, volume_free, now()),
        )
    else:
        conn.execute(
            "UPDATE disks SET label=?, drive_letter=?, volume_serial=?, file_system=?, volume_size=?, volume_free=?, updated_at=? "
            "WHERE disk_id=?",
            (label, drive_letter, volume_serial, file_system, volume_size, volume_free, now(), disk_id),
        )
    conn.commit()
    return created


def get_disk(conn: sqlite3.Connection, disk_id: str) -> Optional[sqlite3.Row]:
    return conn.execute("SELECT * FROM disks WHERE disk_id=?", (disk_id,)).fetchone()


def list_disks(conn: sqlite3.Connection) -> list[sqlite3.Row]:
    return conn.execute("SELECT * FROM disks ORDER BY label, drive_letter").fetchall()


def set_disk_status(
    conn: sqlite3.Connection,
    disk_id: str,
    status: str,
    message: str = "",
) -> None:
    conn.execute(
        "UPDATE disks SET status=?, last_error=?, updated_at=? WHERE disk_id=?",
        (status, message[:500], now(), disk_id),
    )
    conn.commit()


def set_disk_mount(conn: sqlite3.Connection, disk_id: str, drive_letter: str, label: str) -> None:
    conn.execute(
        "UPDATE disks SET drive_letter=?, label=?, updated_at=? WHERE disk_id=?",
        (drive_letter, label, now(), disk_id),
    )
    conn.commit()


def set_disk_scan_progress(
    conn: sqlite3.Connection,
    disk_id: str,
    processed: int,
    errors: int,
    skipped: int,
    current: str,
) -> None:
    conn.execute(
        "UPDATE disks SET scan_processed=?, scan_errors=?, scan_skipped=?, scan_current=?, updated_at=? "
        "WHERE disk_id=?",
        (processed, errors, skipped, current[:400], now(), disk_id),
    )
    conn.commit()


def set_disk_scan_start(conn: sqlite3.Connection, disk_id: str, current: str = "") -> None:
    conn.execute(
        "UPDATE disks SET status='scanning', scan_current=?, scan_processed=0, scan_errors=0, "
        "scan_skipped=0, last_scan_started=?, updated_at=? WHERE disk_id=?",
        (current, now(), now(), disk_id),
    )
    conn.commit()


def finish_disk_scan(
    conn: sqlite3.Connection,
    disk_id: str,
    total_files: int,
    total_size: int,
    added: int,
    deleted: int,
    changed: int,
    errors: int,
    skipped: int,
    message: str = "",
) -> None:
    conn.execute(
        "UPDATE disks SET status='completed', total_files=?, total_size=?, last_added=?, last_deleted=?, "
        "last_changed=?, scan_current='', scan_processed=0, scan_errors=?, scan_skipped=?, "
        "last_scan_finished=?, last_error=?, updated_at=? WHERE disk_id=?",
        (total_files, total_size, added, deleted, changed, errors, skipped, now(), message, now(), disk_id),
    )
    conn.commit()


def abort_disk_scan(
    conn: sqlite3.Connection,
    disk_id: str,
    message: str = "",
) -> None:
    conn.execute(
        "UPDATE disks SET status='partial', last_error=?, updated_at=? WHERE disk_id=?",
        (message[:500], now(), disk_id),
    )
    conn.commit()


def delete_disk_index(conn: sqlite3.Connection, disk_id: str) -> None:
    conn.execute("DELETE FROM files WHERE disk_id=?", (disk_id,))
    conn.execute("DELETE FROM scan_queue WHERE job_id IN (SELECT job_id FROM scan_jobs WHERE disk_id=?)", (disk_id,))
    conn.execute("DELETE FROM scan_jobs WHERE disk_id=?", (disk_id,))
    conn.execute("DELETE FROM scan_log WHERE disk_id=?", (disk_id,))
    conn.execute("DELETE FROM scan_requests WHERE disk_id=?", (disk_id,))
    conn.execute("DELETE FROM disks WHERE disk_id=?", (disk_id,))
    conn.commit()


def clear_all_indexes(conn: sqlite3.Connection) -> None:
    conn.execute("DELETE FROM files")
    conn.execute("DELETE FROM scan_queue")
    conn.execute("DELETE FROM scan_jobs")
    conn.execute("DELETE FROM scan_log")
    conn.execute("DELETE FROM scan_requests")
    conn.execute("DELETE FROM disks")
    conn.commit()


# ---------------- scan jobs / queue ----------------


def create_or_resume_job(
    conn: sqlite3.Connection,
    disk_id: str,
    force: bool = False,
) -> tuple[int, bool]:
    """返回 (job_id, resumed)。force=True 时废弃旧任务并开新任务。"""
    if not force:
        row = conn.execute(
            "SELECT job_id FROM scan_jobs "
            "WHERE disk_id=? AND status IN ('pending','running','aborted') "
            "AND EXISTS (SELECT 1 FROM scan_queue q WHERE q.job_id=scan_jobs.job_id) "
            "ORDER BY job_id DESC LIMIT 1",
            (disk_id,),
        ).fetchone()
        if row:
            job_id = row["job_id"]
            conn.execute(
                "UPDATE scan_jobs SET status='pending', message='续扫', updated_at=? WHERE job_id=?",
                (now(), job_id),
            )
            conn.commit()
            return job_id, True

    # 废弃旧的未完成任务
    old = conn.execute(
        "SELECT job_id FROM scan_jobs WHERE disk_id=? AND status IN ('pending','running','aborted')",
        (disk_id,),
    ).fetchall()
    for row in old:
        conn.execute("DELETE FROM scan_queue WHERE job_id=?", (row["job_id"],))
        conn.execute("DELETE FROM scan_jobs WHERE job_id=?", (row["job_id"],))

    cur = conn.execute(
        "INSERT INTO scan_jobs(disk_id, status, mode, started_at, updated_at) VALUES(?, 'pending', ?, ?, ?)",
        (disk_id, "full" if force else "incremental", now(), now()),
    )
    conn.commit()
    return int(cur.lastrowid), False


def enqueue_dirs(conn: sqlite3.Connection, job_id: int, dir_paths: Iterable[str]) -> None:
    items = list(dir_paths)
    if not items:
        return
    row = conn.execute(
        "SELECT COALESCE(MAX(seq), 0) AS m FROM scan_queue WHERE job_id=?",
        (job_id,),
    ).fetchone()
    seq = row["m"] + 1
    conn.executemany(
        "INSERT INTO scan_queue(job_id, seq, dir_path) VALUES(?,?,?)",
        [(job_id, seq + i, path) for i, path in enumerate(items)],
    )
    conn.commit()


def peek_next_dir(conn: sqlite3.Connection, job_id: int) -> Optional[sqlite3.Row]:
    """取队列头部目录（不删除），保证崩溃/中断后该目录可重扫。"""
    return conn.execute(
        "SELECT seq, dir_path FROM scan_queue WHERE job_id=? ORDER BY seq LIMIT 1",
        (job_id,),
    ).fetchone()


def finish_dir(
    conn: sqlite3.Connection,
    job_id: int,
    seq: int,
    dir_path: str,
    subdirs: Iterable[str],
    entries: Iterable[tuple[Any, ...]],
) -> None:
    """原子完成一个目录：写入条目、追加子目录队列、移除当前队列项。"""
    upsert_entries(conn, job_id=job_id, disk_id=conn.execute(
        "SELECT disk_id FROM scan_jobs WHERE job_id=?", (job_id,)
    ).fetchone()["disk_id"], entries=entries)

    items = list(subdirs)
    if items:
        row = conn.execute(
            "SELECT COALESCE(MAX(seq), 0) AS m FROM scan_queue WHERE job_id=?",
            (job_id,),
        ).fetchone()
        seq_start = row["m"] + 1
        conn.executemany(
            "INSERT INTO scan_queue(job_id, seq, dir_path) VALUES(?,?,?)",
            [(job_id, seq_start + i, path) for i, path in enumerate(items)],
        )

    conn.execute("DELETE FROM scan_queue WHERE job_id=? AND seq=?", (job_id, seq))
    conn.commit()


def queue_size(conn: sqlite3.Connection, job_id: int) -> int:
    return conn.execute("SELECT COUNT(*) AS c FROM scan_queue WHERE job_id=?", (job_id,)).fetchone()["c"]


def touch_job(
    conn: sqlite3.Connection,
    job_id: int,
    processed: int,
    errors: int,
    skipped: int,
    current: str,
) -> None:
    conn.execute(
        "UPDATE scan_jobs SET status='running', processed=?, errors=?, skipped=?, current_path=?, "
        "updated_at=? WHERE job_id=?",
        (processed, errors, skipped, current[:400], now(), job_id),
    )


def finish_job(conn: sqlite3.Connection, job_id: int, message: str = "") -> None:
    conn.execute(
        "UPDATE scan_jobs SET status='completed', finished_at=?, message=?, updated_at=? WHERE job_id=?",
        (now(), message, now(), job_id),
    )


def abort_job(conn: sqlite3.Connection, job_id: int, message: str) -> None:
    conn.execute(
        "UPDATE scan_jobs SET status='aborted', message=?, updated_at=? WHERE job_id=?",
        (message, now(), job_id),
    )


# ---------------- scan requests ----------------


def request_scan(conn: sqlite3.Connection, disk_id: str, mode: str = "incremental") -> bool:
    """入队扫描请求；已排队/执行中则忽略。返回 True 表示新入队。"""
    row = conn.execute(
        "SELECT id FROM scan_requests WHERE disk_id=? AND status IN ('queued','running') LIMIT 1",
        (disk_id,),
    ).fetchone()
    if row:
        if mode != "full":
            return False
        conn.execute(
            "UPDATE scan_requests SET status='superseded' WHERE id=?",
            (row["id"],),
        )
    conn.execute(
        "INSERT INTO scan_requests(disk_id, mode, requested_at, status) VALUES(?,?,?,'queued')",
        (disk_id, mode, now()),
    )
    conn.commit()
    return True


def take_scan_request(conn: sqlite3.Connection) -> Optional[sqlite3.Row]:
    row = conn.execute(
        "SELECT * FROM scan_requests WHERE status='queued' ORDER BY id LIMIT 1"
    ).fetchone()
    if row is None:
        return None
    conn.execute("UPDATE scan_requests SET status='running' WHERE id=?", (row["id"],))
    conn.commit()
    return row


def finish_scan_request(conn: sqlite3.Connection, request_id: int, ok: bool, message: str = "") -> None:
    conn.execute(
        "UPDATE scan_requests SET status=?, message=? WHERE id=?",
        ("done" if ok else "failed", message[:500], request_id),
    )
    conn.commit()


# ---------------- scan lock ----------------


def try_acquire_scan_lock(conn: sqlite3.Connection, pid: int, stale_after: int = 240) -> bool:
    conn.execute(
        "INSERT OR IGNORE INTO scan_lock(id, pid, started_at, last_heartbeat) VALUES(1, ?, ?, ?)",
        (pid, now(), now()),
    )
    row = conn.execute("SELECT * FROM scan_lock WHERE id=1").fetchone()
    if row["pid"] == pid:
        conn.execute("UPDATE scan_lock SET last_heartbeat=? WHERE id=1", (now(),))
        conn.commit()
        return True
    if now() - row["last_heartbeat"] > stale_after:
        conn.execute(
            "UPDATE scan_lock SET pid=?, started_at=?, last_heartbeat=? WHERE id=1",
            (pid, now(), now()),
        )
        conn.commit()
        return True
    conn.commit()
    return False


def heartbeat_scan_lock(conn: sqlite3.Connection, pid: int) -> None:
    conn.execute("UPDATE scan_lock SET last_heartbeat=? WHERE id=1 AND pid=?", (now(), pid))
    conn.commit()


def release_scan_lock(conn: sqlite3.Connection, pid: int) -> None:
    conn.execute("DELETE FROM scan_lock WHERE id=1 AND pid=?", (pid,))
    conn.commit()


# ---------------- files ----------------


def upsert_entries(conn: sqlite3.Connection, disk_id: str, job_id: int, entries: Iterable[tuple[Any, ...]]) -> None:
    """批量写入扫描结果。entries 为 (path,name,parent,is_dir,size,mtime,ext,hidden,system)。"""
    rows = [
        (disk_id, path, name, parent, int(is_dir), int(size or 0), int(mtime or 0), ext, int(hidden), int(system), job_id)
        for path, name, parent, is_dir, size, mtime, ext, hidden, system in entries
    ]
    if not rows:
        return
    conn.executemany(
        """
        INSERT INTO files(disk_id, path, name, parent, is_dir, size, mtime, ext, hidden, system, seen_session)
        VALUES(?,?,?,?,?,?,?,?,?,?,?)
        ON CONFLICT(disk_id, path) DO UPDATE SET
            name=excluded.name,
            parent=excluded.parent,
            is_dir=excluded.is_dir,
            size=excluded.size,
            mtime=excluded.mtime,
            ext=excluded.ext,
            hidden=excluded.hidden,
            system=excluded.system,
            seen_session=excluded.seen_session
        """,
        rows,
    )


def count_files(conn: sqlite3.Connection, disk_id: str) -> int:
    return conn.execute("SELECT COUNT(*) AS c FROM files WHERE disk_id=?", (disk_id,)).fetchone()["c"]


def count_size(conn: sqlite3.Connection, disk_id: str) -> int:
    return conn.execute(
        "SELECT COALESCE(SUM(size),0) AS s FROM files WHERE disk_id=? AND is_dir=0",
        (disk_id,),
    ).fetchone()["s"]


def delete_unseen(conn: sqlite3.Connection, disk_id: str, job_id: int) -> int:
    row = conn.execute(
        "SELECT COUNT(*) AS c FROM files WHERE disk_id=? AND seen_session<>?",
        (disk_id, job_id),
    ).fetchone()
    deleted = row["c"]
    conn.execute("DELETE FROM files WHERE disk_id=? AND seen_session<>?", (disk_id, job_id))
    conn.commit()
    return deleted


def insert_scan_log(
    conn: sqlite3.Connection,
    disk_id: str,
    job_id: int,
    mode: str,
    started_at: int,
    finished_at: int,
    total_found: int,
    added: int,
    deleted: int,
    changed: int,
    errors: int,
    skipped: int,
    aborted: int = 0,
    message: str = "",
) -> None:
    conn.execute(
        """
        INSERT INTO scan_log(disk_id, job_id, mode, started_at, finished_at, total_found, added, deleted,
                             changed, errors, skipped, aborted, message)
        VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)
        """,
        (disk_id, job_id, mode, started_at, finished_at, total_found, added, deleted, changed, errors, skipped,
         aborted, message),
    )
    conn.commit()
