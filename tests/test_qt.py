"""PySide6 界面层冒烟测试（offscreen，无需显示器）。"""

import os
import tempfile
import unittest
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication

from diskmenu import db
from diskmenu.gui import MainWindow
from diskmenu.qt_models import FileFilterProxyModel, FileTableModel
from diskmenu.qt_theme import apply_theme
from diskmenu.qt_widgets import DirTreeWidget

app = QApplication.instance() or QApplication([])


ROWS = [
    {"path": "readme.md", "name": "readme.md", "is_dir": False, "size": 120, "mtime": 1786695900, "ext": "md"},
    {"path": "Movies", "name": "Movies", "is_dir": True, "size": 0, "mtime": 1786695900, "ext": ""},
    {"path": "Movies/Sub", "name": "Sub", "is_dir": True, "size": 0, "mtime": 1786695900, "ext": ""},
    {"path": "Movies/a.txt", "name": "a.txt", "is_dir": False, "size": 2048, "mtime": 1786695900, "ext": "txt"},
    {"path": "Movies/b.mp4", "name": "b.mp4", "is_dir": False, "size": 5 * 1024 * 1024, "mtime": 1786700000, "ext": "mp4"},
]


def _seed_db(db_path: Path, disk_id: str = "vol:QT") -> None:
    conn = db.connect(str(db_path))
    db.init_db(conn)
    db.ensure_disk(conn, disk_id, label="QtDisk", drive_letter="E:")
    for r in ROWS:
        conn.execute(
            "INSERT OR REPLACE INTO files(disk_id,path,name,parent,is_dir,size,mtime,ext) VALUES (?,?,?,?,?,?,?,?)",
            (disk_id, r["path"], r["name"], r["path"].rsplit("/", 1)[0] if "/" in r["path"] else "", int(r["is_dir"]), r["size"], r["mtime"], r["ext"]),
        )
    conn.commit()
    conn.close()


class QtModelTests(unittest.TestCase):
    def setUp(self):
        self.model = FileTableModel()
        self.model.set_rows([dict(r) for r in ROWS])
        self.proxy = FileFilterProxyModel()
        self.proxy.setSourceModel(self.model)

    def test_keyword_filter(self):
        self.proxy.set_filters(keyword=".txt")
        self.assertEqual(self.proxy.rowCount(), 1)

    def test_ext_filter(self):
        self.proxy.set_filters(ext="mp4")
        self.assertEqual(self.proxy.rowCount(), 1)

    def test_size_filter(self):
        self.proxy.set_filters(size_min=2048)
        self.assertEqual(self.proxy.rowCount(), 2)  # a.txt + b.mp4（目录 size=0 被过滤）

    def test_sort_size_desc(self):
        self.proxy.sort(1, Qt.AscendingOrder)
        names = [self.proxy.index(i, 0).data(Qt.DisplayRole) for i in range(self.proxy.rowCount())]
        self.assertEqual(names[0], "Movies")  # 升序时目录优先
        self.proxy.sort(1, Qt.DescendingOrder)
        names = [self.proxy.index(i, 0).data(Qt.DisplayRole) for i in range(self.proxy.rowCount())]
        self.assertLess(names.index("b.mp4"), names.index("a.txt"))

    def test_sort_name_nocase(self):
        self.proxy.sort(0, Qt.AscendingOrder)
        names = [self.proxy.index(i, 0).data(Qt.DisplayRole) for i in range(self.proxy.rowCount())]
        self.assertEqual(names, ["Movies", "Sub", "a.txt", "b.mp4", "readme.md"])


class QtWidgetTests(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="diskmenu-qt-"))
        self.db_path = self.tmp / "index.db"
        _seed_db(self.db_path)
        self.conn = db.connect(str(self.db_path))

    def tearDown(self):
        try:
            self.conn.close()
        except Exception:
            pass

    def test_dir_tree_lazy_load(self):
        tree = DirTreeWidget(self.conn)
        tree.set_disk("vol:QT")
        self.assertEqual(tree.topLevelItemCount(), 1)
        item = tree.topLevelItem(0)
        self.assertEqual(item.data(0, Qt.UserRole), "Movies")
        self.assertEqual(item.childCount(), 1)  # 懒加载占位
        tree.set_disk("")
        self.assertEqual(tree.topLevelItemCount(), 0)

    def test_main_window_offscreen(self):
        win = MainWindow(str(self.db_path))
        self.assertTrue(win.authenticated)
        self.assertEqual(win.model.rowCount(), 2)  # 根目录下：readme.md + Movies
        win._poll_timer.stop()
        win._show_timer.stop()
        win.conn.close()
        win.deleteLater()

    def test_theme_apply(self):
        apply_theme(app, "dark")
        apply_theme(app, "light")


if __name__ == "__main__":
    unittest.main()
