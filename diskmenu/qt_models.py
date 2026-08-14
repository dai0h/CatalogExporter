"""Qt 数据模型：文件列表表格模型 + 排序/过滤代理模型。"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Optional

from PySide6.QtCore import QAbstractTableModel, QModelIndex, QSortFilterProxyModel, Qt


def format_size(size: int) -> str:
    if size < 1024:
        return f"{size} B"
    units = ["KB", "MB", "GB", "TB", "PB"]
    value = float(size)
    for unit in units:
        value /= 1024.0
        if value < 1024 or unit == units[-1]:
            return f"{value:.1f} {unit}"
    return f"{size} B"


def parse_size(text: str) -> Optional[int]:
    text = (text or "").strip().lower()
    if not text:
        return None
    try:
        if text.endswith("kb"):
            return int(float(text[:-2]) * 1024)
        if text.endswith("mb"):
            return int(float(text[:-2]) * 1024 * 1024)
        if text.endswith("gb"):
            return int(float(text[:-2]) * 1024 * 1024 * 1024)
        if text.endswith("tb"):
            return int(float(text[:-2]) * 1024 * 1024 * 1024 * 1024)
        return int(float(text))
    except ValueError:
        return None


def format_time(ts: Optional[int]) -> str:
    if not ts:
        return "-"
    try:
        return datetime.fromtimestamp(ts).strftime("%Y-%m-%d %H:%M")
    except Exception:
        return "-"


class FileTableModel(QAbstractTableModel):
    """文件列表模型。列：名称 / 大小 / 修改时间 / 类型 / 完整路径。"""

    COLUMNS = [
        ("name", "名称"),
        ("size", "大小"),
        ("mtime", "修改时间"),
        ("ext", "类型"),
        ("path", "完整路径"),
    ]

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._rows: list[dict[str, Any]] = []

    # ---------------- data ----------------

    def set_rows(self, rows: list[dict[str, Any]]) -> None:
        self.beginResetModel()
        self._rows = rows
        self.endResetModel()

    def clear(self) -> None:
        self.set_rows([])

    def rowCount(self, parent: QModelIndex = QModelIndex()) -> int:
        return 0 if parent.isValid() else len(self._rows)

    def columnCount(self, parent: QModelIndex = QModelIndex()) -> int:
        return 0 if parent.isValid() else len(self.COLUMNS)

    def data(self, index: QModelIndex, role: int = Qt.DisplayRole) -> Any:
        if not index.isValid() or not (0 <= index.row() < len(self._rows)):
            return None
        row = self._rows[index.row()]
        key = self.COLUMNS[index.column()][0]
        if role == Qt.UserRole:
            return row.get(key)
        if role == Qt.UserRole + 1:
            return row
        if role == Qt.DisplayRole:
            value = row.get(key)
            if key == "name":
                return row["name"]
            if key == "size":
                return "-" if row.get("is_dir") else format_size(value or 0)
            if key == "mtime":
                return format_time(value)
            if key == "ext":
                return "目录" if row.get("is_dir") else (value or "-")
            return value or ""
        if role == Qt.TextAlignmentRole and key == "size":
            return int(Qt.AlignRight | Qt.AlignVCenter)
        return None

    def headerData(self, section: int, orientation: Qt.Orientation, role: int = Qt.DisplayRole) -> Any:
        if role != Qt.DisplayRole:
            return None
        if orientation == Qt.Horizontal and 0 <= section < len(self.COLUMNS):
            return self.COLUMNS[section][1]
        return None

    # ---------------- helpers ----------------

    def row_info(self, row: int) -> Optional[dict[str, Any]]:
        if 0 <= row < len(self._rows):
            return self._rows[row]
        return None

    def path_of(self, row: int) -> str:
        info = self.row_info(row)
        return info["path"] if info else ""

    def is_dir_row(self, row: int) -> bool:
        info = self.row_info(row)
        return bool(info and info.get("is_dir"))


class FileFilterProxyModel(QSortFilterProxyModel):
    """支持关键字/类型/大小/日期筛选与列排序的代理模型。"""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setDynamicSortFilter(True)
        self.keyword = ""
        self.ext = ""
        self.size_min: Optional[int] = None
        self.size_max: Optional[int] = None
        self.date_from: Optional[int] = None
        self.date_to: Optional[int] = None

    def set_filters(
        self,
        keyword: str = "",
        ext: str = "",
        size_min: Optional[int] = None,
        size_max: Optional[int] = None,
        date_from: Optional[int] = None,
        date_to: Optional[int] = None,
    ) -> None:
        self.keyword = keyword.strip().lower()
        self.ext = ext.strip().lower().lstrip(".")
        self.size_min = size_min
        self.size_max = size_max
        self.date_from = date_from
        self.date_to = date_to
        self.invalidateFilter()

    def clear_filters(self) -> None:
        self.set_filters()

    def filterAcceptsRow(self, source_row: int, source_parent: QModelIndex) -> bool:
        model = self.sourceModel()
        if model is None:
            return True
        index = model.index(source_row, 0, source_parent)
        info = model.data(index, Qt.UserRole + 1)
        if not info:
            return False
        name = (info.get("name") or "").lower()
        path = (info.get("path") or "").lower()
        if self.keyword and self.keyword not in name and self.keyword not in path:
            return False
        ext = (info.get("ext") or "").lower()
        if self.ext and ext != self.ext:
            return False
        size = int(info.get("size") or 0)
        if self.size_min is not None and size < self.size_min:
            return False
        if self.size_max is not None and size > self.size_max:
            return False
        mtime = int(info.get("mtime") or 0)
        if self.date_from is not None and mtime < self.date_from:
            return False
        if self.date_to is not None and mtime > self.date_to:
            return False
        return True

    def lessThan(self, left: QModelIndex, right: QModelIndex) -> bool:
        col = left.column()
        info_a = left.data(Qt.UserRole + 1) or {}
        info_b = right.data(Qt.UserRole + 1) or {}
        # 与 v1.2 一致：目录始终排在文件前面
        if bool(info_a.get("is_dir")) != bool(info_b.get("is_dir")):
            return bool(info_a.get("is_dir"))
        key = FileTableModel.COLUMNS[col][0]
        a = info_a.get(key)
        b = info_b.get(key)
        if col in (1, 2):  # size / mtime 数值排序
            ia = int(a or 0)
            ib = int(b or 0)
            if ia != ib:
                return ia < ib
        else:
            sa = str(a or "").lower()
            sb = str(b or "").lower()
            if sa != sb:
                return sa < sb
        # 稳定排序：同值按名称兜底
        return str(info_a.get("name") or "").lower() < str(info_b.get("name") or "").lower()
