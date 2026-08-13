"""核心功能冒烟测试：增量扫描、断点续扫、HTML 导出。"""

import os
import tempfile
import threading
import unittest
from pathlib import Path

from diskmenu import db
from diskmenu.exporter import export_html
from diskmenu.scanner import scan_disk


def _prepare_disk(root: Path, db_path: Path, disk_id: str = "vol:TEST") -> None:
    conn = db.connect(db_path)
    db.init_db(conn)
    (root / "Movies").mkdir()
    (root / "Movies" / "a.txt").write_text("hello")
    (root / "Photos").mkdir()
    (root / "Photos" / "b.jpg").write_bytes(b"123")
    (root / "readme.md").write_text("x")
    db.ensure_disk(conn, disk_id, label="TestDisk", drive_letter=str(root))
    conn.execute("UPDATE disks SET drive_letter=? WHERE disk_id=?", (str(root), disk_id))
    conn.commit()
    conn.close()


class CoreTests(unittest.TestCase):
    def setUp(self):
        self.root = Path(tempfile.mkdtemp(prefix="diskmenu-test-"))
        self.db_path = self.root / "index.db"

    def tearDown(self):
        pass

    def test_scan_incremental_and_stats(self):
        disk_root = self.root / "disk"
        disk_root.mkdir()
        _prepare_disk(disk_root, self.db_path)
        ok, msg = scan_disk("vol:TEST", db_path=str(self.db_path))
        self.assertTrue(ok, msg)
        conn = db.connect(self.db_path)
        row = db.get_disk(conn, "vol:TEST")
        self.assertEqual(row["status"], "completed")
        self.assertEqual(row["total_files"], 3)  # 3 个文件，目录不计入

        (disk_root / "Movies" / "a.txt").unlink()
        (disk_root / "new.dat").write_text("new")
        ok, msg = scan_disk("vol:TEST", db_path=str(self.db_path))
        self.assertTrue(ok, msg)
        row = db.get_disk(conn, "vol:TEST")
        self.assertEqual(row["last_added"], 1)
        self.assertEqual(row["last_deleted"], 1)
        paths = {r["path"] for r in conn.execute("SELECT path FROM files WHERE disk_id='vol:TEST'")}
        self.assertIn("new.dat", paths)
        self.assertNotIn("Movies/a.txt", paths)
        conn.close()

    def test_scan_resume_after_abort(self):
        disk_root = self.root / "disk"
        disk_root.mkdir()
        _prepare_disk(disk_root, self.db_path)
        stop = threading.Event()

        def stop_after_first(info):
            if info["processed"] >= 1:
                stop.set()

        ok, msg = scan_disk("vol:TEST", db_path=str(self.db_path), on_progress=stop_after_first, stop_event=stop)
        self.assertFalse(ok)
        conn = db.connect(self.db_path)
        row = db.get_disk(conn, "vol:TEST")
        self.assertEqual(row["status"], "partial")
        conn.close()

        ok, msg = scan_disk("vol:TEST", db_path=str(self.db_path))
        self.assertTrue(ok, msg)
        conn = db.connect(self.db_path)
        row = db.get_disk(conn, "vol:TEST")
        self.assertEqual(row["status"], "completed")
        self.assertEqual(row["total_files"], 3)
        conn.close()

    def test_export_html(self):
        disk_root = self.root / "disk"
        disk_root.mkdir()
        _prepare_disk(disk_root, self.db_path)
        scan_disk("vol:TEST", db_path=str(self.db_path))
        out = self.root / "report.html"
        ok, msg = export_html(str(self.db_path), "vol:TEST", out)
        self.assertTrue(ok, msg)
        content = out.read_text(encoding="utf-8")
        self.assertIn("readme.md", content)
        self.assertIn("const DATA =", content)
        self.assertIn('id="tree"', content)
        self.assertIn("navigateTo", content)
        self.assertIn("file-icon", content)
        self.assertIn("ext-badge", content)
        self.assertIn('id="view"', content)
        self.assertIn("renderGrid", content)
        self.assertIn("cap-bar", content)
        self.assertIn("table-layout: fixed", content)
        self.assertIn('id="splitter"', content)
        self.assertIn("resizer", content)
        self.assertIn('id="panelResize"', content)
        self.assertIn('id="resizeEast"', content)
        self.assertIn('id="resizeSouth"', content)

    def test_service_auto_export(self):
        from diskmenu.service import DiskMenuService

        disk_root = self.root / "disk"
        disk_root.mkdir()
        _prepare_disk(disk_root, self.db_path)
        scan_disk("vol:TEST", db_path=str(self.db_path))
        export_dir = self.root / "exports"
        conn = db.connect(self.db_path)
        conn.execute("UPDATE disks SET drive_letter='C:' WHERE disk_id='vol:TEST'")
        conn.commit()
        db.set_setting(conn, "auto_export_on_insert", "1")
        db.set_setting(conn, "auto_export_dir", str(export_dir))
        svc = DiskMenuService(db_path=str(self.db_path))
        out = svc._auto_export(conn, "vol:TEST", "insert")
        self.assertIsNotNone(out)
        self.assertTrue(Path(out).exists())
        parent = Path(out).parent
        self.assertTrue(parent.name.startswith("c盘"))
        self.assertIn("vol_test", parent.name)
        conn.close()


if __name__ == "__main__":
    unittest.main()
