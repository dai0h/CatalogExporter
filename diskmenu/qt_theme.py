"""PySide6 主题：浅色/深色 QSS 与 SVG 图标加载。"""

from __future__ import annotations

from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QApplication

from .paths import asset_path

THEMES = ("light", "dark")


LIGHT_QSS = """
* {
    font-family: "Microsoft YaHei UI", "Microsoft YaHei", "Segoe UI";
    font-size: 13px;
    color: #1f2937;
}
QWidget { background: transparent; }
QMainWindow, QDialog { background: #f3f6fb; }
QSplitter { background: #f3f6fb; }
QSplitter::handle { background: #e2e8f0; }
QFrame#HeaderBar { background: #ffffff; border-bottom: 1px solid #e2e8f0; }
QFrame[card="true"] { background: #ffffff; border: 1px solid #e2e8f0; border-radius: 10px; }
QLabel#AppTitle { font-size: 17px; font-weight: 700; color: #1e3a8a; }
QLabel#AppSubtitle { font-size: 11px; color: #64748b; }
QLabel#SectionTitle { font-size: 12px; font-weight: 700; color: #334155; }
QLabel#StatsLabel { color: #475569; }
QListWidget#DiskList { background: transparent; border: none; outline: none; }
QListWidget#DiskList::item { border: none; background: transparent; }
QFrame[diskCard="true"] { background: #ffffff; border: 1px solid #e2e8f0; border-radius: 10px; }
QFrame[diskCard="true"]:hover { border-color: #93c5fd; background: #f8fafc; }
QFrame[diskCardActive="true"] { border-color: #2563eb; background: #eff6ff; }
QLabel[diskName="true"] { font-size: 12px; font-weight: 700; color: #1f2937; }
QLabel[diskSub="true"] { font-size: 11px; color: #64748b; }
QTreeWidget#DirTree, QTableView#FileTable {
    background: #ffffff; alternate-background-color: #f8fafc;
    border: 1px solid #e2e8f0; border-radius: 8px; selection-background-color: #dbeafe;
    selection-color: #1e3a8a; outline: none;
}
QTreeWidget#DirTree::item, QTableView#FileTable::item { padding: 2px 4px; }
QTreeWidget#DirTree::item:hover, QTableView#FileTable::item:hover { background: #f1f5f9; }
QHeaderView::section {
    background: #eef2f7; color: #334155; font-weight: 700; padding: 7px 8px;
    border: none; border-right: 1px solid #e2e8f0; border-bottom: 1px solid #e2e8f0;
}
QLineEdit, QComboBox {
    background: #ffffff; border: 1px solid #cbd5e1; border-radius: 8px; padding: 5px 9px;
    selection-background-color: #bfdbfe;
}
QLineEdit:focus, QComboBox:focus { border-color: #2563eb; }
QPushButton {
    background: #e2e8f0; color: #1f2937; border: none; border-radius: 8px; padding: 7px 14px;
}
QPushButton:hover { background: #cbd5e1; }
QPushButton:pressed { background: #b6c2d1; }
QPushButton#PrimaryButton { background: #2563eb; color: #ffffff; font-weight: 600; }
QPushButton#PrimaryButton:hover { background: #1d4ed8; }
QPushButton#DangerButton { background: #fee2e2; color: #b91c1c; }
QPushButton#DangerButton:hover { background: #fecaca; }
QToolButton#IconButton {
    background: transparent; border: none; border-radius: 8px; padding: 5px;
}
QToolButton#IconButton:hover { background: #e2e8f0; }
QCheckBox { spacing: 7px; }
QCheckBox::indicator { width: 17px; height: 17px; border-radius: 5px; border: 1px solid #cbd5e1; background: #ffffff; }
QCheckBox::indicator:checked { background: #2563eb; border-color: #2563eb; image: url(assets/icons/check.svg); }
QMenu { background: #ffffff; border: 1px solid #e2e8f0; border-radius: 8px; padding: 5px; }
QMenu::item { padding: 7px 26px; border-radius: 6px; }
QMenu::item:selected { background: #e2e8f0; }
QMenu::separator { height: 1px; background: #e2e8f0; margin: 5px 8px; }
QStatusBar { background: #ffffff; border-top: 1px solid #e2e8f0; color: #475569; }
QScrollBar:vertical { background: transparent; width: 10px; margin: 0; }
QScrollBar::handle:vertical { background: #cbd5e1; border-radius: 5px; min-height: 30px; }
QScrollBar::handle:vertical:hover { background: #94a3b8; }
QScrollBar:horizontal { background: transparent; height: 10px; margin: 0; }
QScrollBar::handle:horizontal { background: #cbd5e1; border-radius: 5px; min-width: 30px; }
QScrollBar::add-line, QScrollBar::sub-line { height: 0; width: 0; }
QScrollBar::add-page, QScrollBar::sub-page { background: transparent; }
QMessageBox { background: #ffffff; }
QDialog QLabel { background: transparent; }
"""


DARK_QSS = """
* {
    font-family: "Microsoft YaHei UI", "Microsoft YaHei", "Segoe UI";
    font-size: 13px;
    color: #e5e7eb;
}
QWidget { background: transparent; }
QMainWindow, QDialog { background: #0f172a; }
QSplitter { background: #0f172a; }
QSplitter::handle { background: #334155; }
QFrame#HeaderBar { background: #1e293b; border-bottom: 1px solid #334155; }
QFrame[card="true"] { background: #1e293b; border: 1px solid #334155; border-radius: 10px; }
QLabel#AppTitle { font-size: 17px; font-weight: 700; color: #93c5fd; }
QLabel#AppSubtitle { font-size: 11px; color: #94a3b8; }
QLabel#SectionTitle { font-size: 12px; font-weight: 700; color: #cbd5e1; }
QLabel#StatsLabel { color: #94a3b8; }
QListWidget#DiskList { background: transparent; border: none; outline: none; }
QListWidget#DiskList::item { border: none; background: transparent; }
QFrame[diskCard="true"] { background: #1e293b; border: 1px solid #334155; border-radius: 10px; }
QFrame[diskCard="true"]:hover { border-color: #3b82f6; background: #243349; }
QFrame[diskCardActive="true"] { border-color: #3b82f6; background: #172554; }
QLabel[diskName="true"] { font-size: 12px; font-weight: 700; color: #e5e7eb; }
QLabel[diskSub="true"] { font-size: 11px; color: #94a3b8; }
QTreeWidget#DirTree, QTableView#FileTable {
    background: #1e293b; alternate-background-color: #1a2535;
    border: 1px solid #334155; border-radius: 8px; selection-background-color: #1e3a5f;
    selection-color: #dbeafe; outline: none;
}
QTreeWidget#DirTree::item, QTableView#FileTable::item { padding: 2px 4px; }
QTreeWidget#DirTree::item:hover, QTableView#FileTable::item:hover { background: #273549; }
QHeaderView::section {
    background: #243349; color: #cbd5e1; font-weight: 700; padding: 7px 8px;
    border: none; border-right: 1px solid #334155; border-bottom: 1px solid #334155;
}
QLineEdit, QComboBox {
    background: #0f172a; border: 1px solid #475569; border-radius: 8px; padding: 5px 9px;
    selection-background-color: #1d4ed8; color: #e5e7eb;
}
QLineEdit:focus, QComboBox:focus { border-color: #3b82f6; }
QPushButton {
    background: #334155; color: #e5e7eb; border: none; border-radius: 8px; padding: 7px 14px;
}
QPushButton:hover { background: #475569; }
QPushButton:pressed { background: #52657c; }
QPushButton#PrimaryButton { background: #2563eb; color: #ffffff; font-weight: 600; }
QPushButton#PrimaryButton:hover { background: #3b82f6; }
QPushButton#DangerButton { background: #451a1a; color: #fca5a5; }
QPushButton#DangerButton:hover { background: #5b2020; }
QToolButton#IconButton { background: transparent; border: none; border-radius: 8px; padding: 5px; }
QToolButton#IconButton:hover { background: #334155; }
QCheckBox { spacing: 7px; }
QCheckBox::indicator { width: 17px; height: 17px; border-radius: 5px; border: 1px solid #475569; background: #0f172a; }
QCheckBox::indicator:checked { background: #2563eb; border-color: #2563eb; image: url(assets/icons/check.svg); }
QMenu { background: #1e293b; border: 1px solid #334155; border-radius: 8px; padding: 5px; }
QMenu::item { padding: 7px 26px; border-radius: 6px; }
QMenu::item:selected { background: #334155; }
QMenu::separator { height: 1px; background: #334155; margin: 5px 8px; }
QStatusBar { background: #1e293b; border-top: 1px solid #334155; color: #94a3b8; }
QScrollBar:vertical { background: transparent; width: 10px; margin: 0; }
QScrollBar::handle:vertical { background: #475569; border-radius: 5px; min-height: 30px; }
QScrollBar::handle:vertical:hover { background: #64748b; }
QScrollBar:horizontal { background: transparent; height: 10px; margin: 0; }
QScrollBar::handle:horizontal { background: #475569; border-radius: 5px; min-width: 30px; }
QScrollBar::add-line, QScrollBar::sub-line { height: 0; width: 0; }
QScrollBar::add-page, QScrollBar::sub-page { background: transparent; }
QMessageBox { background: #1e293b; }
QDialog QLabel { background: transparent; }
"""


def apply_theme(app: QApplication, theme: str) -> None:
    """应用浅色/深色主题样式表。"""
    app.setStyle("Fusion")
    app.setStyleSheet(DARK_QSS if theme == "dark" else LIGHT_QSS)


def icon(name: str) -> QIcon:
    """加载 assets/icons/<name>.svg 图标。"""
    path = asset_path("icons") / f"{name}.svg"
    if path.exists():
        return QIcon(str(path))
    return QIcon()
