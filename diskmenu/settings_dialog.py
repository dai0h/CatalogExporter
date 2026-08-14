"""设置对话框：扫描选项、自动导出规则、开机自启、主题与索引密码。"""

from __future__ import annotations

import hashlib
import secrets

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QFileDialog,
    QFormLayout,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
)

from . import autostart, db
from .qt_theme import THEMES


def hash_password(password: str) -> str:
    salt = secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt.encode("utf-8"), 100_000).hex()
    return f"{salt}${digest}"


def verify_password(password: str, stored: str) -> bool:
    try:
        salt, digest = stored.split("$", 1)
    except ValueError:
        return False
    test = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt.encode("utf-8"), 100_000).hex()
    return secrets.compare_digest(test, digest)


class SettingsDialog(QDialog):
    """设置窗口。保存后自动处理开机自启与密码。"""

    settings_saved = Signal(dict)

    def __init__(self, conn, parent=None) -> None:
        super().__init__(parent)
        self.conn = conn
        self.setWindowTitle("设置")
        self.setModal(True)
        self.resize(520, 620)
        settings = db.get_settings(conn)

        root = QVBoxLayout(self)
        root.setContentsMargins(16, 16, 16, 16)
        root.setSpacing(12)

        # ---------------- 扫描选项 ----------------
        scan_box = self._group("扫描选项")
        self.start_check = QCheckBox("开机自动启动（后台托盘运行）")
        self.hidden_check = QCheckBox("扫描隐藏文件（默认关闭）")
        self.system_check = QCheckBox("扫描系统文件（默认关闭）")
        self.removable_check = QCheckBox("自动扫描可移动盘（U 盘等）")
        self.fixed_check = QCheckBox("自动扫描固定盘（含本地硬盘、USB 硬盘盒）")
        self.ignore_edit = QLineEdit()
        self.extra_edit = QLineEdit()
        form = QFormLayout()
        form.addRow(self.start_check)
        form.addRow(self.hidden_check)
        form.addRow(self.system_check)
        form.addRow(self.removable_check)
        form.addRow(self.fixed_check)
        form.addRow("忽略的盘符（如 D:,E:，逗号分隔）", self.ignore_edit)
        form.addRow("强制视为外接盘的盘符（可选）", self.extra_edit)
        scan_box.layout().addLayout(form)
        root.addWidget(scan_box)

        # ---------------- 自动导出 ----------------
        export_box = self._group("自动导出 HTML 报告")
        self.auto_boot_check = QCheckBox("开机时自动导出所有已索引硬盘的报告")
        self.auto_insert_check = QCheckBox("插入硬盘并扫描完成后自动导出该硬盘的报告")
        export_dir_row = QHBoxLayout()
        self.export_dir_edit = QLineEdit()
        pick_btn = QPushButton("选择文件夹")
        pick_btn.clicked.connect(self._choose_dir)
        export_dir_row.addWidget(self.export_dir_edit, 1)
        export_dir_row.addWidget(pick_btn)
        hint = QLabel("导出目录不存在时会自动创建；每块盘按“盘符盘_usb_序列号”保存到子文件夹。")
        hint.setWordWrap(True)
        hint.setStyleSheet("color: #64748b; font-size: 11px;")
        export_form = QFormLayout()
        export_form.addRow(self.auto_boot_check)
        export_form.addRow(self.auto_insert_check)
        export_form.addRow("导出目录", export_dir_row)
        export_box.layout().addLayout(export_form)
        export_box.layout().addWidget(hint)
        root.addWidget(export_box)

        # ---------------- 外观与安全 ----------------
        misc_box = self._group("外观与安全")
        misc_form = QFormLayout()
        self.theme_combo = QComboBox()
        self.theme_combo.addItem("浅色", "light")
        self.theme_combo.addItem("深色", "dark")
        misc_form.addRow("界面主题", self.theme_combo)
        self.password_edit = QLineEdit()
        self.password_edit.setEchoMode(QLineEdit.Password)
        misc_form.addRow("索引密码（可选，留空不修改）", self.password_edit)
        pwd_hint = QLabel("提示：设置密码后，打开主界面需要输入密码。")
        pwd_hint.setStyleSheet("color: #64748b; font-size: 11px;")
        misc_box.layout().addLayout(misc_form)
        misc_box.layout().addWidget(pwd_hint)
        root.addWidget(misc_box)

        # ---------------- 按钮 ----------------
        btns = QHBoxLayout()
        btns.addStretch(1)
        cancel_btn = QPushButton("取消")
        cancel_btn.clicked.connect(self.reject)
        save_btn = QPushButton("保存")
        save_btn.setObjectName("PrimaryButton")
        save_btn.clicked.connect(self._save)
        btns.addWidget(cancel_btn)
        btns.addWidget(save_btn)
        root.addLayout(btns)

        # ---------------- 初始值 ----------------
        self.start_check.setChecked(settings.get("start_at_login", "0") == "1")
        self.hidden_check.setChecked(settings.get("scan_hidden", "0") == "1")
        self.system_check.setChecked(settings.get("scan_system", "0") == "1")
        self.removable_check.setChecked(settings.get("scan_removable", "1") == "1")
        self.fixed_check.setChecked(settings.get("scan_fixed_new", "1") == "1")
        self.ignore_edit.setText(settings.get("ignore_drives", ""))
        self.extra_edit.setText(settings.get("extra_external", ""))
        self.auto_boot_check.setChecked(settings.get("auto_export_on_boot", "0") == "1")
        self.auto_insert_check.setChecked(settings.get("auto_export_on_insert", "0") == "1")
        self.export_dir_edit.setText(settings.get("auto_export_dir", ""))
        theme = settings.get("ui_theme", "light")
        idx = self.theme_combo.findData(theme if theme in THEMES else "light")
        self.theme_combo.setCurrentIndex(max(0, idx))

    def _group(self, title: str) -> QFrame:
        box = QFrame()
        box.setProperty("card", True)
        lay = QVBoxLayout(box)
        lay.setContentsMargins(14, 12, 14, 12)
        lay.setSpacing(8)
        head = QLabel(title)
        head.setObjectName("SectionTitle")
        lay.addWidget(head)
        return box

    def _choose_dir(self) -> None:
        start = self.export_dir_edit.text().strip() or None
        chosen = QFileDialog.getExistingDirectory(self, "选择自动导出文件夹", start or "")
        if chosen:
            self.export_dir_edit.setText(chosen)

    def _save(self) -> None:
        values = {
            "start_at_login": "1" if self.start_check.isChecked() else "0",
            "scan_hidden": "1" if self.hidden_check.isChecked() else "0",
            "scan_system": "1" if self.system_check.isChecked() else "0",
            "scan_removable": "1" if self.removable_check.isChecked() else "0",
            "scan_fixed_new": "1" if self.fixed_check.isChecked() else "0",
            "ignore_drives": self.ignore_edit.text().strip(),
            "extra_external": self.extra_edit.text().strip(),
            "auto_export_on_boot": "1" if self.auto_boot_check.isChecked() else "0",
            "auto_export_on_insert": "1" if self.auto_insert_check.isChecked() else "0",
            "auto_export_dir": self.export_dir_edit.text().strip(),
            "ui_theme": self.theme_combo.currentData() or "light",
        }
        if (values["auto_export_on_boot"] == "1" or values["auto_export_on_insert"] == "1") and not values["auto_export_dir"]:
            QMessageBox.warning(self, "提示", "请先选择自动导出的文件夹")
            return
        pwd = self.password_edit.text()
        if pwd:
            values["password_hash"] = hash_password(pwd)
        db.set_settings_many(self.conn, values)
        try:
            if values["start_at_login"] == "1":
                autostart.install()
                if not autostart.is_installed():
                    QMessageBox.warning(self, "开机自启", "开机自启可能未生效，请检查杀毒软件或权限设置。")
            else:
                autostart.uninstall()
        except Exception as exc:
            QMessageBox.warning(self, "开机自启", f"设置开机自启失败：{exc}")
        self.settings_saved.emit(values)
        self.accept()
