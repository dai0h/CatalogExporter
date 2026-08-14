"""PySide6 主界面：左侧硬盘卡片 + 目录树，右侧文件列表，支持搜索、排序、筛选、统计与维护。"""

from __future__ import annotations

import os
import sys
import threading
from datetime import datetime
from typing import Optional

from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtGui import QCloseEvent, QIcon
from PySide6.QtWidgets import (
    QApplication,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QHeaderView,
    QInputDialog,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QMenu,
    QMessageBox,
    QPushButton,
    QSplitter,
    QTableView,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from . import db
from .exporter import export_html
from .paths import APP_TITLE, icon_path
from .qt_models import FileFilterProxyModel, FileTableModel, format_size, format_time, parse_size
from .qt_theme import apply_theme, icon
from .qt_widgets import DirTreeWidget, DiskCardWidget
from .settings_dialog import SettingsDialog, verify_password
from .single_instance import SingleInstance
from .util import safe_filename

_LIMIT = 50_000
_SHOW_EVENT = "Local\\CatalogExporterV2Show"

WAIT_OBJECT_0 = 0


def _signal_show() -> None:
    """通知已存在的（隐藏）主窗口显示。"""
    import ctypes

    kernel32 = ctypes.windll.kernel32
    handle = kernel32.CreateEventW(None, False, False, _SHOW_EVENT)
    if handle:
        kernel32.SetEvent(handle)
        kernel32.CloseHandle(handle)


def _tray_running() -> bool:
    try:
        return SingleInstance.is_running("CatalogExporterV2Tray")
    except Exception:
        return False


class MainWindow(QMainWindow):
    """目录导出管家主窗口。"""

    export_finished = Signal(bool, str, str)

    def __init__(self, db_path: Optional[str] = None) -> None:
        super().__init__()
        self.db_path = db_path
        self.conn = db.connect(db_path)
        db.init_db(self.conn)
        self.settings = db.get_settings(self.conn)

        # 密码保护
        self.authenticated = True
        if self.settings.get("password_hash"):
            if not self._ask_password():
                self.authenticated = False
                self.conn.close()
                return

        app = QApplication.instance()
        if app is not None:
            apply_theme(app, self.settings.get("ui_theme", "light"))

        self.current_disk: Optional[str] = None
        self.current_dir = ""
        self.search_mode = False
        self._selected_disk_id: Optional[str] = None
        self._known_disk_ids: set[str] = set()
        self._show_handle = None

        self.setWindowTitle(APP_TITLE)
        self.resize(1180, 720)
        self.setMinimumSize(940, 580)
        try:
            self.setWindowIcon(QIcon(str(icon_path())))
        except Exception:
            pass

        self._build_ui()
        self.refresh_disks()
        self.export_finished.connect(self._on_export_done)

        self._poll_timer = QTimer(self)
        self._poll_timer.setInterval(2000)
        self._poll_timer.timeout.connect(self._poll_status)
        self._poll_timer.start()

        self._show_timer = QTimer(self)
        self._show_timer.setInterval(800)
        self._show_timer.timeout.connect(self._check_show_event)
        self._show_timer.start()
        try:
            import ctypes

            self._show_handle = ctypes.windll.kernel32.CreateEventW(None, False, False, _SHOW_EVENT)
        except Exception:
            self._show_handle = None

    # ---------------- 密码 ----------------

    def _ask_password(self) -> bool:
        text, ok = QInputDialog.getText(
            self,
            "输入密码",
            "该索引已设置密码保护，请输入密码：",
            QLineEdit.Password,
        )
        return ok and verify_password(text, self.settings["password_hash"])

    # ---------------- UI ----------------

    def _build_ui(self) -> None:
        central = QWidget()
        self.setCentralWidget(central)
        root = QVBoxLayout(central)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        root.addWidget(self._build_header())

        splitter = QSplitter(Qt.Horizontal)
        splitter.setChildrenCollapsible(False)
        splitter.setHandleWidth(6)
        splitter.addWidget(self._build_left_panel())
        splitter.addWidget(self._build_right_panel())
        splitter.setStretchFactor(0, 2)
        splitter.setStretchFactor(1, 5)
        splitter.setSizes([360, 820])
        root.addWidget(splitter, 1)

        self.status_label = QLabel("就绪")
        self.statusBar().addWidget(self.status_label, 1)

    def _build_header(self) -> QFrame:
        header = QFrame()
        header.setObjectName("HeaderBar")
        layout = QHBoxLayout(header)
        layout.setContentsMargins(18, 12, 18, 12)
        layout.setSpacing(8)

        title_box = QVBoxLayout()
        title_box.setSpacing(2)
        title = QLabel(APP_TITLE)
        title.setObjectName("AppTitle")
        subtitle = QLabel("插盘自动扫描 · 拔盘离线浏览 · 一键导出 HTML")
        subtitle.setObjectName("AppSubtitle")
        title_box.addWidget(title)
        title_box.addWidget(subtitle)
        layout.addLayout(title_box, 1)

        self.theme_btn = QToolButton()
        self.theme_btn.setObjectName("IconButton")
        self.theme_btn.setToolTip("切换浅色/深色主题")
        self.theme_btn.clicked.connect(self.toggle_theme)
        layout.addWidget(self.theme_btn)
        self._update_theme_icon()

        self.refresh_btn = QToolButton()
        self.refresh_btn.setObjectName("IconButton")
        self.refresh_btn.setIcon(icon("refresh"))
        self.refresh_btn.setToolTip("刷新")
        self.refresh_btn.clicked.connect(self.refresh_disks)
        layout.addWidget(self.refresh_btn)

        self.clear_btn = QPushButton("清空全部")
        self.clear_btn.setToolTip("清空所有硬盘的索引记录")
        self.clear_btn.clicked.connect(self.clear_all)
        layout.addWidget(self.clear_btn)

        self.delete_btn = QPushButton("删除索引")
        self.delete_btn.setObjectName("DangerButton")
        self.delete_btn.setToolTip("删除当前选中硬盘的索引")
        self.delete_btn.clicked.connect(self.delete_current)
        layout.addWidget(self.delete_btn)

        self.rescan_btn = QPushButton("重新完整扫描")
        self.rescan_btn.setIcon(icon("scan"))
        self.rescan_btn.clicked.connect(self.rescan_current)
        layout.addWidget(self.rescan_btn)

        self.settings_btn = QPushButton("设置")
        self.settings_btn.setIcon(icon("settings"))
        self.settings_btn.clicked.connect(self.open_settings)
        layout.addWidget(self.settings_btn)

        self.export_btn = QPushButton("导出 HTML")
        self.export_btn.setObjectName("PrimaryButton")
        self.export_btn.setIcon(icon("export"))
        self.export_btn.clicked.connect(self.export_current)
        layout.addWidget(self.export_btn)
        return header

    def _build_left_panel(self) -> QFrame:
        panel = QFrame()
        panel.setProperty("card", True)
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(8)

        disks_title = QLabel("硬盘")
        disks_title.setObjectName("SectionTitle")
        layout.addWidget(disks_title)

        self.disk_list = QListWidget()
        self.disk_list.setObjectName("DiskList")
        self.disk_list.setMaximumHeight(300)
        self.disk_list.setSpacing(4)
        self.disk_list.setSelectionMode(QListWidget.NoSelection)
        layout.addWidget(self.disk_list)

        dirs_title = QLabel("目录")
        dirs_title.setObjectName("SectionTitle")
        layout.addWidget(dirs_title)

        self.tree = DirTreeWidget(self.conn)
        self.tree.dir_selected.connect(self._on_tree_dir)
        layout.addWidget(self.tree, 1)
        return panel

    def _build_right_panel(self) -> QFrame:
        panel = QFrame()
        panel.setProperty("card", True)
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(8)

        toolbar = QHBoxLayout()
        toolbar.setSpacing(6)
        self.search_edit = QLineEdit()
        self.search_edit.setPlaceholderText("搜索文件名或路径…")
        self.search_edit.setClearButtonEnabled(True)
        self.search_edit.returnPressed.connect(self._search)
        toolbar.addWidget(self.search_edit, 1)

        search_btn = QPushButton("搜索")
        search_btn.clicked.connect(self._search)
        toolbar.addWidget(search_btn)
        clear_btn = QPushButton("清空")
        clear_btn.clicked.connect(self._clear_search)
        toolbar.addWidget(clear_btn)

        toolbar.addWidget(self._filter_label("类型:"))
        self.ext_edit = QLineEdit()
        self.ext_edit.setFixedWidth(76)
        toolbar.addWidget(self.ext_edit)

        toolbar.addWidget(self._filter_label("大小:"))
        self.size_min_edit = QLineEdit()
        self.size_min_edit.setFixedWidth(72)
        self.size_min_edit.setPlaceholderText("如 1MB")
        toolbar.addWidget(self.size_min_edit)
        toolbar.addWidget(self._filter_label("~"))
        self.size_max_edit = QLineEdit()
        self.size_max_edit.setFixedWidth(72)
        toolbar.addWidget(self.size_max_edit)

        toolbar.addWidget(self._filter_label("日期:"))
        self.date_from_edit = QLineEdit()
        self.date_from_edit.setFixedWidth(96)
        self.date_from_edit.setPlaceholderText("2026-01-01")
        toolbar.addWidget(self.date_from_edit)
        toolbar.addWidget(self._filter_label("~"))
        self.date_to_edit = QLineEdit()
        self.date_to_edit.setFixedWidth(96)
        toolbar.addWidget(self.date_to_edit)

        apply_btn = QPushButton("应用筛选")
        apply_btn.clicked.connect(self._apply_filter)
        toolbar.addWidget(apply_btn)
        layout.addLayout(toolbar)

        self.stats_label = QLabel("请选择左侧硬盘")
        self.stats_label.setObjectName("StatsLabel")
        layout.addWidget(self.stats_label)

        self.model = FileTableModel(self)
        self.proxy = FileFilterProxyModel(self)
        self.proxy.setSourceModel(self.model)

        self.table = QTableView()
        self.table.setObjectName("FileTable")
        self.table.setModel(self.proxy)
        self.table.setAlternatingRowColors(True)
        self.table.setSelectionBehavior(QTableView.SelectRows)
        self.table.setSelectionMode(QTableView.SingleSelection)
        self.table.setEditTriggers(QTableView.NoEditTriggers)
        self.table.setSortingEnabled(True)
        self.table.verticalHeader().setVisible(False)
        self.table.verticalHeader().setDefaultSectionSize(30)
        self.table.setContextMenuPolicy(Qt.CustomContextMenu)
        self.table.customContextMenuRequested.connect(self._on_table_menu)
        self.table.doubleClicked.connect(self._on_table_double)

        header = self.table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.Interactive)
        header.setSectionResizeMode(1, QHeaderView.Fixed)
        header.setSectionResizeMode(2, QHeaderView.Fixed)
        header.setSectionResizeMode(3, QHeaderView.Fixed)
        header.setSectionResizeMode(4, QHeaderView.Stretch)
        self.table.setColumnWidth(0, 320)
        self.table.setColumnWidth(1, 110)
        self.table.setColumnWidth(2, 150)
        self.table.setColumnWidth(3, 90)
        self.table.sortByColumn(0, Qt.AscendingOrder)
        layout.addWidget(self.table, 1)
        return panel

    @staticmethod
    def _filter_label(text: str) -> QLabel:
        label = QLabel(text)
        label.setStyleSheet("color: #64748b;")
        return label

    # ---------------- 硬盘与目录 ----------------

    def refresh_disks(self) -> None:
        disks = db.list_disks(self.conn)
        self._known_disk_ids = {row["disk_id"] for row in disks}
        self.disk_list.clear()
        for row in disks:
            item = QListWidgetItem()
            card = DiskCardWidget(row)
            card.clicked.connect(self._select_disk)
            item.setSizeHint(card.sizeHint())
            self.disk_list.addItem(item)
            self.disk_list.setItemWidget(item, card)
        if disks:
            if self._selected_disk_id not in self._known_disk_ids:
                self._selected_disk_id = disks[0]["disk_id"]
            self._select_disk(self._selected_disk_id, refresh_tree=True)
        else:
            self.current_disk = None
            self._selected_disk_id = None
            self.tree.set_disk("")
            self._load_entries()

    def _select_disk(self, disk_id: str, refresh_tree: bool = True) -> None:
        self._selected_disk_id = disk_id
        self.current_disk = disk_id
        self.current_dir = ""
        self.search_mode = False
        for i in range(self.disk_list.count()):
            card = self.disk_list.itemWidget(self.disk_list.item(i))
            if card is not None:
                card.set_active(getattr(card, "disk_id", None) == disk_id)
        if refresh_tree:
            self.tree.set_disk(disk_id)
        self._load_entries()
        self._update_stats()

    def _on_tree_dir(self, path: str) -> None:
        if self.current_disk is None:
            return
        self.current_dir = path
        self.search_mode = False
        self._load_entries()

    # ---------------- 文件列表 ----------------

    def _load_entries(self) -> None:
        self.model.clear()
        if not self.current_disk:
            self.stats_label.setText("请选择左侧硬盘")
            return
        disk_id = self.current_disk
        where = ["disk_id=?"]
        params: list = [disk_id]

        if not self.search_mode:
            where.append("parent=?")
            params.append(self.current_dir)
        else:
            keyword = self.search_edit.text().strip()
            if keyword:
                where.append("(name LIKE ? OR path LIKE ?)")
                like = f"%{keyword}%"
                params.extend([like, like])

        sql = (
            "SELECT path,name,is_dir,size,mtime,ext FROM files "
            f"WHERE {' AND '.join(where)} "
            "ORDER BY is_dir DESC, name COLLATE NOCASE ASC LIMIT ?"
        )
        rows = self.conn.execute(sql, params + [_LIMIT]).fetchall()
        self.model.set_rows(
            [
                {
                    "path": r["path"],
                    "name": r["name"],
                    "is_dir": bool(r["is_dir"]),
                    "size": r["size"],
                    "mtime": r["mtime"],
                    "ext": r["ext"],
                }
                for r in rows
            ]
        )
        self._apply_filter_to_proxy()
        if len(rows) >= _LIMIT:
            self.status_label.setText(f"结果较多，仅显示前 {_LIMIT:,} 条；请使用搜索或筛选缩小范围")
        else:
            self.status_label.setText("就绪")

    def _apply_filter_to_proxy(self) -> None:
        if not self.search_mode:
            self.proxy.set_filters()
            return
        size_min = parse_size(self.size_min_edit.text())
        size_max = parse_size(self.size_max_edit.text())
        date_from = self._parse_date(self.date_from_edit.text(), end_of_day=False)
        date_to = self._parse_date(self.date_to_edit.text(), end_of_day=True)
        self.proxy.set_filters(
            keyword=self.search_edit.text(),
            ext=self.ext_edit.text(),
            size_min=size_min,
            size_max=size_max,
            date_from=date_from,
            date_to=date_to,
        )

    @staticmethod
    def _parse_date(text: str, end_of_day: bool = False) -> Optional[int]:
        text = text.strip()
        if not text:
            return None
        try:
            if end_of_day:
                dt = datetime.strptime(text + " 23:59:59", "%Y-%m-%d %H:%M:%S")
            else:
                dt = datetime.strptime(text, "%Y-%m-%d")
            return int(dt.timestamp())
        except ValueError:
            return None

    def _search(self) -> None:
        if not self.current_disk:
            return
        self.search_mode = True
        self._load_entries()

    def _clear_search(self) -> None:
        self.search_edit.clear()
        self.ext_edit.clear()
        self.size_min_edit.clear()
        self.size_max_edit.clear()
        self.date_from_edit.clear()
        self.date_to_edit.clear()
        self.search_mode = False
        self._load_entries()

    def _apply_filter(self) -> None:
        self.search_mode = True
        self._load_entries()

    def _update_stats(self) -> None:
        if not self.current_disk:
            self.stats_label.setText("请选择左侧硬盘")
            return
        row = db.get_disk(self.conn, self.current_disk)
        if row is None:
            self.stats_label.setText("该硬盘索引已被删除")
            return
        name = row["label"].strip() or "未命名硬盘"
        serial = f" · 序列号 {row['volume_serial']}" if row["volume_serial"] else ""
        self.stats_label.setText(
            f"{name}（{row['drive_letter'] or '未连接'}{serial}）· 文件 {row['total_files']:,} 个 · "
            f"总大小 {format_size(row['total_size'])} · 上次扫描 {format_time(row['last_scan_finished'])} · "
            f"上次新增 {row['last_added']} / 删除 {row['last_deleted']}"
        )

    # ---------------- 表格交互 ----------------

    def _on_table_double(self, index) -> None:
        if not index.isValid():
            return
        src = self.proxy.mapToSource(index)
        if self.model.is_dir_row(src.row()):
            self.tree.reveal_path(self.model.path_of(src.row()))

    def _on_table_menu(self, pos) -> None:
        index = self.table.indexAt(pos)
        if not index.isValid():
            return
        src = self.proxy.mapToSource(index)
        path = self.model.path_of(src.row())
        if not path:
            return
        self.table.selectRow(index.row())
        menu = QMenu(self)
        action = menu.addAction("复制完整路径")
        chosen = menu.exec(self.table.viewport().mapToGlobal(pos))
        if chosen is action:
            self._copy_path(path)

    def _copy_path(self, path: str) -> None:
        if not self.current_disk:
            return
        text = path
        row = db.get_disk(self.conn, self.current_disk)
        if row and row["drive_letter"]:
            text = f"{row['drive_letter'].rstrip('\\')}\\{path.replace('/', '\\')}"
        QApplication.clipboard().setText(text)

    # ---------------- 操作 ----------------

    def rescan_current(self) -> None:
        if not self.current_disk:
            QMessageBox.information(self, "提示", "请先在左侧选择一块硬盘")
            return
        if (
            QMessageBox.question(
                self,
                "重新扫描",
                "将重新完整扫描这块硬盘（只读，不修改盘上文件），继续吗？",
            )
            != QMessageBox.Yes
        ):
            return
        from .scanner import scan_disk

        disk_id = self.current_disk
        db.request_scan(self.conn, disk_id, "full")
        if _tray_running():
            self.status_label.setText("已加入完整扫描队列")
        else:
            self.status_label.setText("正在完整扫描…")
            threading.Thread(
                target=scan_disk,
                kwargs={"disk_id": disk_id, "mode": "full", "db_path": self.db_path},
                daemon=True,
            ).start()
        self.refresh_disks()

    def export_current(self) -> None:
        if not self.current_disk:
            QMessageBox.information(self, "提示", "请先在左侧选择一块硬盘")
            return
        disk = db.get_disk(self.conn, self.current_disk)
        if disk is None:
            return
        serial = disk["volume_serial"] or ""
        base = safe_filename(disk["label"].strip() or f"{disk['drive_letter'].replace(':', '')}_{serial}")
        default = f"DiskMenu_{base}_{datetime.now():%Y%m%d_%H%M}.html"
        path, _ = QFileDialog.getSaveFileName(
            self,
            "导出为 HTML 离线报告",
            default,
            "HTML 文件 (*.html)",
        )
        if not path:
            return
        disk_id = self.current_disk
        self.status_label.setText("正在导出…")
        self.setCursor(Qt.WaitCursor)

        def work():
            ok, msg = export_html(self.db_path, disk_id, path)
            self.export_finished.emit(ok, msg, path)

        threading.Thread(target=work, daemon=True).start()

    def _on_export_done(self, ok: bool, msg: str, path: str) -> None:
        self.setCursor(Qt.ArrowCursor)
        if ok:
            self.status_label.setText("导出完成")
            if (
                QMessageBox.question(self, "导出完成", f"已导出到：\n{msg}\n\n是否立即打开？")
                == QMessageBox.Yes
            ):
                try:
                    os.startfile(msg)  # type: ignore[attr-defined]
                except Exception:
                    pass
        else:
            QMessageBox.critical(self, "导出失败", msg)
            self.status_label.setText("导出失败")

    def delete_current(self) -> None:
        if not self.current_disk:
            return
        if (
            QMessageBox.question(
                self,
                "删除索引",
                "将删除这块硬盘的全部索引，之后如需浏览需重新插盘扫描。确定？",
            )
            == QMessageBox.Yes
        ):
            db.delete_disk_index(self.conn, self.current_disk)
            self.refresh_disks()
            self.status_label.setText("索引已删除")

    def clear_all(self) -> None:
        if (
            QMessageBox.question(
                self,
                "清空全部索引",
                "将清空所有硬盘的索引记录，确定？",
            )
            == QMessageBox.Yes
        ):
            db.clear_all_indexes(self.conn)
            self.refresh_disks()
            self.status_label.setText("已清空全部索引")

    # ---------------- 设置与主题 ----------------

    def open_settings(self) -> None:
        dialog = SettingsDialog(self.conn, self)
        dialog.settings_saved.connect(self._on_settings_saved)
        dialog.exec()

    def _on_settings_saved(self, values: dict) -> None:
        self.settings = db.get_settings(self.conn)
        self._update_theme_icon()
        self.status_label.setText("设置已保存")
        self.refresh_disks()

    def toggle_theme(self) -> None:
        theme = "dark" if self.settings.get("ui_theme", "light") != "dark" else "light"
        db.set_setting(self.conn, "ui_theme", theme)
        self.settings = db.get_settings(self.conn)
        app = QApplication.instance()
        if app is not None:
            apply_theme(app, theme)
        self._update_theme_icon()

    def _update_theme_icon(self) -> None:
        dark = self.settings.get("ui_theme", "light") == "dark"
        self.theme_btn.setIcon(icon("sun" if dark else "moon"))
        self.theme_btn.setToolTip("切换到浅色主题" if dark else "切换到深色主题")

    # ---------------- 轮询与事件 ----------------

    def _poll_status(self) -> None:
        try:
            rows = db.list_disks(self.conn)
            scanning = [r for r in rows if r["status"] in ("scanning", "queued")]
            ids = {r["disk_id"] for r in rows}
            if ids != self._known_disk_ids:
                self.refresh_disks()
                return
            if scanning:
                r = scanning[0]
                name = r["label"].strip() or r["drive_letter"] or "硬盘"
                self.status_label.setText(
                    f"{name} 扫描中：已处理 {r['scan_processed']} 个目录，当前 {r['scan_current'] or '…'}"
                )
            elif self.status_label.text().startswith(("扫描", "正在")):
                self.status_label.setText("就绪")
            self._update_stats()
        except Exception:
            pass

    def _check_show_event(self) -> None:
        handle = self._show_handle
        if handle:
            try:
                import ctypes

                if ctypes.windll.kernel32.WaitForSingleObject(handle, 0) == WAIT_OBJECT_0:
                    self.showNormal()
                    self.raise_()
                    self.activateWindow()
            except Exception:
                pass

    def closeEvent(self, event: QCloseEvent) -> None:
        if _tray_running():
            event.ignore()
            self.hide()
            return
        event.accept()
        try:
            self.conn.close()
        finally:
            app = QApplication.instance()
            if app is not None:
                app.quit()


def run(db_path: Optional[str] = None) -> None:
    """PySide6 主程序入口。"""
    try:
        from PySide6.QtGui import QGuiApplication

        QGuiApplication.setHighDpiScaleFactorRoundingPolicy(
            Qt.HighDpiScaleFactorRoundingPolicy.PassThrough
        )
    except Exception:
        pass

    app = QApplication.instance() or QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)
    app.setApplicationName(APP_TITLE)

    instance = SingleInstance("CatalogExporterV2App")
    if not instance.acquire():
        _signal_show()
        return
    try:
        window = MainWindow(db_path)
        if not window.authenticated:
            return
        window.show()
        app.exec()
    finally:
        instance.release()
