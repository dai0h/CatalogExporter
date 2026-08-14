"""Qt 自定义控件：硬盘卡片、懒加载目录树。"""

from __future__ import annotations

from typing import Optional

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QFrame, QLabel, QTreeWidget, QTreeWidgetItem, QVBoxLayout

from . import db
from .qt_models import format_size
from .qt_theme import icon

STATUS_TEXT = {
    "completed": "已索引",
    "scanning": "扫描中",
    "queued": "等待扫描",
    "partial": "部分索引",
    "error": "出错",
    "removed": "未连接",
    "none": "未扫描",
}


class DiskCardWidget(QFrame):
    """左侧硬盘卡片。"""

    clicked = Signal(str)

    def __init__(self, row, parent=None) -> None:
        super().__init__(parent)
        self.setProperty("diskCard", True)
        self.disk_id = row["disk_id"]
        self.setCursor(Qt.PointingHandCursor)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 8, 10, 8)
        layout.setSpacing(2)

        serial = f" · 序列号 {row['volume_serial']}" if row["volume_serial"] else ""
        title = (row["label"].strip() or "未命名硬盘") + f"  ({row['drive_letter'] or '未连接'}{serial})"
        status_text = STATUS_TEXT.get(row["status"], row["status"])
        sub = f"{status_text} · {row['total_files']:,} 个文件 · {format_size(row['total_size'])}"

        self.title_lbl = QLabel(title)
        self.title_lbl.setProperty("diskName", True)
        self.sub_lbl = QLabel(sub)
        self.sub_lbl.setProperty("diskSub", True)
        self.sub_lbl.setWordWrap(False)
        layout.addWidget(self.title_lbl)
        layout.addWidget(self.sub_lbl)
        self.set_active(False)

    def set_active(self, active: bool) -> None:
        self.setProperty("diskCardActive", bool(active))
        self.style().unpolish(self)
        self.style().polish(self)

    def mousePressEvent(self, event) -> None:
        if event.button() == Qt.LeftButton:
            self.clicked.emit(self.disk_id)
        super().mousePressEvent(event)


class DirTreeWidget(QTreeWidget):
    """懒加载目录树：展开时才查询子目录。"""

    dir_selected = Signal(str)

    def __init__(self, conn, parent=None) -> None:
        super().__init__(parent)
        self.conn = conn
        self.disk_id = ""
        self.setObjectName("DirTree")
        self.setHeaderHidden(True)
        self.setAnimated(True)
        self._folder_icon = icon("folder")
        self.itemExpanded.connect(self._on_expanded)
        self.currentItemChanged.connect(self._on_current_changed)

    # ---------------- API ----------------

    def set_disk(self, disk_id: str) -> None:
        self.disk_id = disk_id
        self.clear()
        if disk_id:
            self._load_children(None, "")

    def reveal_path(self, path: str) -> None:
        """选中并展开某个目录路径（用于从文件列表双击目录跳转）。"""
        if not self.disk_id:
            return
        parts = [p for p in (path or "").split("/") if p]
        parent = None
        current = ""
        for part in parts:
            current = f"{current}/{part}" if current else part
            item = self._find_child(parent, current)
            if item is None:
                self._load_children(parent, "" if parent is None else parent.data(0, Qt.UserRole))
                item = self._find_child(parent, current)
            if item is None:
                return
            self.expandItem(item)
            parent = item
        if parent is not None:
            self.setCurrentItem(parent)
            self.scrollToItem(parent)

    # ---------------- internals ----------------

    def _on_expanded(self, item: QTreeWidgetItem) -> None:
        if item is None:
            return
        child = item.child(0)
        if child is not None and child.data(0, Qt.UserRole) is None:
            item.removeChild(child)
            parent_path = item.data(0, Qt.UserRole) or ""
            self._load_children(item, parent_path)

    def _on_current_changed(self, current: Optional[QTreeWidgetItem], _previous=None) -> None:
        if current is not None:
            self.dir_selected.emit(current.data(0, Qt.UserRole) or "")

    def _find_child(self, parent: Optional[QTreeWidgetItem], path: str) -> Optional[QTreeWidgetItem]:
        count = parent.childCount() if parent is not None else self.topLevelItemCount()
        for i in range(count):
            item = parent.child(i) if parent is not None else self.topLevelItem(i)
            if item.data(0, Qt.UserRole) == path:
                return item
        return None

    def _load_children(self, parent: Optional[QTreeWidgetItem], parent_path: str) -> None:
        rows = self.conn.execute(
            "SELECT path, name FROM files WHERE disk_id=? AND parent=? AND is_dir=1 "
            "ORDER BY name COLLATE NOCASE",
            (self.disk_id, parent_path),
        ).fetchall()
        for row in rows:
            item = QTreeWidgetItem()
            item.setText(0, row["name"])
            item.setIcon(0, self._folder_icon)
            item.setData(0, Qt.UserRole, row["path"])
            has_child = self.conn.execute(
                "SELECT 1 FROM files WHERE disk_id=? AND parent=? AND is_dir=1 LIMIT 1",
                (self.disk_id, row["path"]),
            ).fetchone()
            if has_child:
                dummy = QTreeWidgetItem()
                dummy.setData(0, Qt.UserRole, None)
                item.addChild(dummy)
            if parent is not None:
                parent.addChild(item)
            else:
                self.addTopLevelItem(item)
