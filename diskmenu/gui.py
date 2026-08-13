"""Tkinter 主界面：左侧目录树 + 右侧文件列表，支持搜索、排序、筛选、统计与维护。"""

from __future__ import annotations

import base64
import ctypes
import hashlib
import os
import secrets
import threading
import tkinter as tk
from datetime import datetime
from tkinter import filedialog, messagebox, ttk
from typing import Optional

from . import db
from .exporter import export_html
from .paths import APP_TITLE, asset_path, icon_path
from .util import safe_filename


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


def _hash_password(password: str) -> str:
    salt = secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt.encode("utf-8"), 100_000).hex()
    return f"{salt}${digest}"


def _verify_password(password: str, stored: str) -> bool:
    try:
        salt, digest = stored.split("$", 1)
    except ValueError:
        return False
    test = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt.encode("utf-8"), 100_000).hex()
    return secrets.compare_digest(test, digest)


def _node_iid(kind: str, disk_id: str, path: str = "") -> str:
    raw = f"{kind}\x00{disk_id}\x00{path}"
    return base64.urlsafe_b64encode(raw.encode("utf-8")).decode("ascii")


def _node_key(iid: str) -> tuple[str, str, str]:
    raw = base64.urlsafe_b64decode(iid.encode("ascii")).decode("utf-8")
    parts = raw.split("\x00", 2)
    return parts[0], parts[1], parts[2] if len(parts) > 2 else ""


def _enable_dpi_awareness() -> None:
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(2)
    except Exception:
        try:
            ctypes.windll.user32.SetProcessDPIAware()
        except Exception:
            pass


class RoundedButton(tk.Canvas):
    """圆角按钮：用 Canvas 绘制，适合现代扁平风格。"""

    def __init__(
        self,
        master,
        text: str,
        command=None,
        bg: str = "#2563eb",
        fg: str = "#ffffff",
        hover: str = "#1d4ed8",
        canvas_bg: str = "#ffffff",
        radius: int = 12,
        font=None,
    ) -> None:
        self._text = text
        self._command = command
        self._fg = fg
        self._font = font or ("Microsoft YaHei UI", 10)
        if bg == "#e2e8f0":
            self._normal_img = "button_secondary"
            self._hover_img = "button_secondary_hover"
        else:
            self._normal_img = "button_primary"
            self._hover_img = "button_primary_hover"
        normal = self._load_img(self._normal_img)
        self._btn_w = normal.width()
        self._btn_h = normal.height()
        super().__init__(
            master,
            width=self._btn_w,
            height=self._btn_h,
            bg=canvas_bg,
            highlightthickness=0,
            bd=0,
            cursor="hand2",
        )
        self._draw(self._normal_img)
        self.bind("<Button-1>", self._on_click)
        self.bind("<Enter>", lambda _e: self._draw(self._hover_img))
        self.bind("<Leave>", lambda _e: self._draw(self._normal_img))

    _image_cache: dict[str, tk.PhotoImage] = {}

    def _load_img(self, name: str) -> tk.PhotoImage:
        if name not in self._image_cache:
            self._image_cache[name] = tk.PhotoImage(file=str(asset_path(name + ".png")))
        return self._image_cache[name]

    def _draw(self, image_name: str) -> None:
        self.delete("all")
        img = self._load_img(image_name)
        self.create_image(self._btn_w // 2, self._btn_h // 2, image=img)
        self.create_text(self._btn_w // 2, self._btn_h // 2, text=self._text, fill=self._fg, font=self._font)

    def _on_click(self, _event) -> None:
        if self._command:
            self._command()


class MainWindow(tk.Tk):
    def __init__(self, db_path: Optional[str] = None) -> None:
        _enable_dpi_awareness()
        super().__init__()
        self.db_path = db_path
        try:
            self.disk_icon = tk.PhotoImage(file=str(asset_path("disk.png")))
            self.folder_icon = tk.PhotoImage(file=str(asset_path("folder.png")))
            self.file_icon = tk.PhotoImage(file=str(asset_path("file.png")))
            self.folder_block = tk.PhotoImage(file=str(asset_path("folder_block.png")))
            self.file_block = tk.PhotoImage(file=str(asset_path("file_block.png")))
        except Exception:
            self.disk_icon = None
            self.folder_icon = None
            self.file_icon = None
            self.folder_block = None
            self.file_block = None
        self.conn = db.connect(db_path)
        db.init_db(self.conn)
        self.settings = db.get_settings(self.conn)

        if self.settings.get("password_hash"):
            if not self._ask_password():
                self.destroy()
                return

        self.current_disk: Optional[str] = None
        self.current_dir = ""
        self.search_mode = False
        self.sort_col = "name"
        self.sort_desc = False
        self._disk_cache: dict[str, str] = {}
        self._known_disk_ids: set[str] = set()
        self._selected_disk_id: Optional[str] = None

        self.title(APP_TITLE)
        self.geometry("1180x720")
        self.minsize(900, 580)
        try:
            self.iconbitmap(default=str(icon_path()))
        except Exception:
            pass
        self._apply_style()
        self._build_ui()
        self.refresh_disks()
        self.after(1500, self._poll_status)
        self.protocol("WM_DELETE_WINDOW", self._on_close)

    # ---------------- modern style ----------------

    def _apply_style(self) -> None:
        self.configure(bg="#f3f6fb")
        try:
            dpi = self.winfo_fpixels("1i")
            self.tk.call("tk", "scaling", dpi / 72.0)
        except Exception:
            pass
        style = ttk.Style(self)
        try:
            style.theme_use("clam")
        except Exception:
            pass

        font = "Microsoft YaHei UI"
        style.configure(".", font=(font, 10), background="#f3f6fb", foreground="#1f2937")
        style.configure("TFrame", background="#f3f6fb")
        style.configure("Card.TFrame", background="#ffffff")
        style.configure("TLabel", background="#f3f6fb", foreground="#1f2937")
        style.configure("Card.TLabel", background="#ffffff", foreground="#1f2937")
        style.configure("Muted.TLabel", background="#f3f6fb", foreground="#64748b")
        style.configure("Title.TLabel", font=(font, 17, "bold"), background="#f3f6fb", foreground="#1e3a8a")
        style.configure("Sub.TLabel", font=(font, 9), background="#f3f6fb", foreground="#64748b")
        style.configure(
            "TButton",
            padding=(12, 7),
            background="#2563eb",
            foreground="#ffffff",
            borderwidth=0,
            focusthickness=0,
        )
        style.map("TButton", background=[("active", "#1d4ed8"), ("disabled", "#c7d2fe")])
        style.configure(
            "Secondary.TButton",
            padding=(12, 7),
            background="#e2e8f0",
            foreground="#1f2937",
            borderwidth=0,
        )
        style.map("Secondary.TButton", background=[("active", "#cbd5e1")])
        style.configure(
            "Treeview",
            background="#ffffff",
            fieldbackground="#ffffff",
            foreground="#1f2937",
            rowheight=30,
            borderwidth=0,
        )
        style.configure(
            "Treeview.Heading",
            background="#eef2f7",
            foreground="#334155",
            font=(font, 10, "bold"),
            padding=(8, 7),
        )
        style.map(
            "Treeview",
            background=[("selected", "#dbeafe")],
            foreground=[("selected", "#1e3a8a")],
        )
        style.configure(
            "Modern.Vertical.TScrollbar",
            background="#cbd5e1",
            troughcolor="#f1f5f9",
            bordercolor="#f1f5f9",
            lightcolor="#cbd5e1",
            darkcolor="#cbd5e1",
            arrowcolor="#64748b",
            relief="flat",
            width=10,
        )
        style.configure(
            "Modern.Horizontal.TScrollbar",
            background="#cbd5e1",
            troughcolor="#f1f5f9",
            bordercolor="#f1f5f9",
            lightcolor="#cbd5e1",
            darkcolor="#cbd5e1",
            arrowcolor="#64748b",
            relief="flat",
            width=10,
        )
        style.configure("TEntry", padding=6, fieldbackground="#ffffff")
        style.configure("TNotebook", background="#f3f6fb", borderwidth=0)

    # ---------------- password ----------------

    def _ask_password(self) -> bool:
        win = tk.Toplevel(self)
        win.title("输入密码")
        win.geometry("340x140")
        win.resizable(False, False)
        win.transient(self)
        win.configure(bg="#f3f6fb")
        result = {"ok": False}

        tk.Label(win, text="该索引已设置密码保护，请输入密码：").pack(pady=(16, 8))
        entry = tk.Entry(win, show="*", width=34)
        entry.pack()
        entry.focus_set()

        def check():
            if _verify_password(entry.get(), self.settings["password_hash"]):
                result["ok"] = True
                win.destroy()
            else:
                messagebox.showerror("密码错误", "密码不正确", parent=win)

        def cancel():
            win.destroy()

        frame = ttk.Frame(win)
        frame.pack(pady=12)
        RoundedButton(frame, text="确定", command=check, canvas_bg="#f3f6fb").pack(side="left", padx=8)
        RoundedButton(
            frame, text="取消", command=cancel,
            bg="#e2e8f0", fg="#1f2937", hover="#cbd5e1", canvas_bg="#f3f6fb",
        ).pack(side="left")
        win.bind("<Return>", lambda e: check())
        win.grab_set()
        self.wait_window(win)
        return result["ok"]

    # ---------------- UI ----------------

    def _build_ui(self) -> None:
        top = ttk.Frame(self, style="Card.TFrame", padding=(16, 12))
        top.pack(fill="x")
        title_box = ttk.Frame(top, style="Card.TFrame")
        title_box.pack(side="left", fill="x", expand=True)
        ttk.Label(title_box, text="目录导出管家", style="Title.TLabel").pack(anchor="w")
        ttk.Label(title_box, text="插盘自动扫描 · 拔盘离线浏览 · 一键导出 HTML", style="Sub.TLabel").pack(anchor="w")
        RoundedButton(top, text="导出 HTML", command=self.export_current, canvas_bg="#ffffff").pack(side="right", padx=4)
        RoundedButton(
            top, text="重新完整扫描", command=self.rescan_current,
            bg="#e2e8f0", fg="#1f2937", hover="#cbd5e1", canvas_bg="#ffffff",
        ).pack(side="right", padx=4)
        RoundedButton(
            top, text="删除索引", command=self.delete_current,
            bg="#e2e8f0", fg="#1f2937", hover="#cbd5e1", canvas_bg="#ffffff",
        ).pack(side="right", padx=4)
        RoundedButton(
            top, text="清空全部", command=self.clear_all,
            bg="#e2e8f0", fg="#1f2937", hover="#cbd5e1", canvas_bg="#ffffff",
        ).pack(side="right", padx=4)
        RoundedButton(
            top, text="设置", command=self.open_settings,
            bg="#e2e8f0", fg="#1f2937", hover="#cbd5e1", canvas_bg="#ffffff",
        ).pack(side="right", padx=4)
        RoundedButton(
            top, text="刷新", command=self.refresh_disks,
            bg="#e2e8f0", fg="#1f2937", hover="#cbd5e1", canvas_bg="#ffffff",
        ).pack(side="right", padx=4)

        paned = ttk.PanedWindow(self, orient="horizontal")
        paned.pack(fill="both", expand=True, padx=8, pady=(4, 4))

        # 左侧目录树
        left = ttk.Frame(paned, style="Card.TFrame", padding=(10, 8))
        paned.add(left, weight=2)
        ttk.Label(left, text="硬盘", style="Card.TLabel", font=("Microsoft YaHei UI", 11, "bold")).pack(anchor="w", padx=4, pady=(0, 6))
        self.disk_cards = ttk.Frame(left, style="Card.TFrame")
        self.disk_cards.pack(fill="x", padx=2)
        ttk.Separator(left).pack(fill="x", pady=8)
        ttk.Label(left, text="目录", style="Card.TLabel", font=("Microsoft YaHei UI", 11, "bold")).pack(anchor="w", padx=4, pady=(0, 6))
        tree_frame = ttk.Frame(left, style="Card.TFrame")
        tree_frame.pack(fill="both", expand=True)
        self.tree = ttk.Treeview(tree_frame, show="tree", selectmode="browse")
        self.tree.pack(side="left", fill="both", expand=True)
        vsb = ttk.Scrollbar(tree_frame, orient="vertical", style="Modern.Vertical.TScrollbar", command=self.tree.yview)
        vsb.pack(side="right", fill="y")
        self.tree.configure(yscrollcommand=vsb.set)
        self.tree.bind("<<TreeviewOpen>>", self._on_tree_open)
        self.tree.bind("<<TreeviewSelect>>", self._on_tree_select)

        # 右侧文件区
        right = ttk.Frame(paned, style="Card.TFrame", padding=(10, 8))
        paned.add(right, weight=5)

        toolbar = ttk.Frame(right, style="Card.TFrame")
        toolbar.pack(fill="x", padx=4, pady=4)
        self.search_var = tk.StringVar()
        self.search_entry = ttk.Entry(toolbar, textvariable=self.search_var, width=24)
        self.search_entry.pack(side="left", padx=2)
        self.search_entry.bind("<Return>", lambda e: self._search())
        RoundedButton(toolbar, text="搜索", command=self._search, canvas_bg="#ffffff").pack(side="left", padx=2)
        RoundedButton(
            toolbar, text="清空", command=self._clear_search,
            bg="#e2e8f0", fg="#1f2937", hover="#cbd5e1", canvas_bg="#ffffff",
        ).pack(side="left", padx=2)

        self.ext_var = tk.StringVar()
        ttk.Label(toolbar, text="类型:", style="Card.TLabel").pack(side="left", padx=(12, 2))
        ttk.Entry(toolbar, textvariable=self.ext_var, width=8).pack(side="left", padx=2)
        self.size_min_var = tk.StringVar()
        ttk.Label(toolbar, text="大小:", style="Card.TLabel").pack(side="left", padx=(8, 2))
        ttk.Entry(toolbar, textvariable=self.size_min_var, width=8).pack(side="left", padx=2)
        ttk.Label(toolbar, text="~", style="Card.TLabel").pack(side="left")
        self.size_max_var = tk.StringVar()
        ttk.Entry(toolbar, textvariable=self.size_max_var, width=8).pack(side="left", padx=2)
        self.date_from_var = tk.StringVar()
        self.date_to_var = tk.StringVar()
        ttk.Label(toolbar, text="日期:", style="Card.TLabel").pack(side="left", padx=(8, 2))
        ttk.Entry(toolbar, textvariable=self.date_from_var, width=10).pack(side="left", padx=2)
        ttk.Label(toolbar, text="~", style="Card.TLabel").pack(side="left")
        ttk.Entry(toolbar, textvariable=self.date_to_var, width=10).pack(side="left", padx=2)
        RoundedButton(
            toolbar, text="应用筛选", command=self._apply_filter,
            bg="#e2e8f0", fg="#1f2937", hover="#cbd5e1", canvas_bg="#ffffff",
        ).pack(side="left", padx=4)

        self.stats_var = tk.StringVar(value="请选择左侧硬盘")
        ttk.Label(right, textvariable=self.stats_var, style="Card.TLabel", foreground="#475569").pack(anchor="w", padx=6, pady=(2, 6))

        table_frame = ttk.Frame(right, style="Card.TFrame")
        table_frame.pack(fill="both", expand=True, padx=4, pady=(4, 2))
        cols = ("size", "mtime", "ext", "path")
        self.table = ttk.Treeview(table_frame, columns=cols, show="tree headings")
        self.table.heading("#0", text="名称", command=lambda: self._sort_by("name"))
        self.table.column("#0", width=300, minwidth=120, anchor="w")
        headings = {
            "size": "大小",
            "mtime": "修改时间",
            "ext": "类型",
            "path": "完整路径",
        }
        widths = {"size": 110, "mtime": 140, "ext": 90, "path": 360}
        for col in cols:
            self.table.heading(col, text=headings[col], command=lambda c=col: self._sort_by(c))
            self.table.column(col, width=widths[col], minwidth=60, anchor="w")
        self.table.column("size", anchor="e")
        self.table.pack(side="left", fill="both", expand=True)
        tvsb = ttk.Scrollbar(table_frame, orient="vertical", style="Modern.Vertical.TScrollbar", command=self.table.yview)
        tvsb.pack(side="right", fill="y")
        thsb = ttk.Scrollbar(table_frame, orient="horizontal", style="Modern.Horizontal.TScrollbar", command=self.table.xview)
        thsb.pack(side="bottom", fill="x")
        self.table.configure(yscrollcommand=tvsb.set, xscrollcommand=thsb.set)
        self.table.tag_configure("dir", foreground="#1d4f9c", font=("Microsoft YaHei", 9, "bold"))
        self.table.bind("<Double-1>", self._on_table_double)
        self.table.bind("<Button-3>", self._on_table_menu)

        self.status_var = tk.StringVar(value="就绪")
        status = ttk.Label(self, textvariable=self.status_var, style="Card.TLabel", anchor="w", padding=(12, 7))
        status.pack(fill="x", side="bottom")

    # ---------------- tree / table helpers ----------------

    def refresh_disks(self) -> None:
        for child in self.disk_cards.winfo_children():
            child.destroy()
        self.tree.delete(*self.tree.get_children())
        disks = db.list_disks(self.conn)
        self._known_disk_ids = {row["disk_id"] for row in disks}
        for row in disks:
            self._build_disk_card(row)
        if disks:
            if self._selected_disk_id not in self._known_disk_ids:
                self._selected_disk_id = disks[0]["disk_id"]
            self._select_disk(self._selected_disk_id, refresh_tree=True)
        else:
            self.current_disk = None
            self._selected_disk_id = None
            self._load_entries()

    def _build_disk_card(self, row) -> None:
        card = tk.Frame(
            self.disk_cards,
            bg="#ffffff",
            padx=8,
            pady=6,
            cursor="hand2",
            highlightthickness=1,
            highlightbackground="#e2e8f0",
        )
        card.pack(fill="x", pady=3)
        card.disk_id = row["disk_id"]
        serial = f" · 序列号 {row['volume_serial']}" if row["volume_serial"] else ""
        title = (row["label"].strip() or "未命名硬盘") + f"  ({row['drive_letter'] or '未连接'}{serial})"
        status_text = {
            "completed": "已索引",
            "scanning": "扫描中",
            "queued": "等待扫描",
            "partial": "部分索引",
            "error": "出错",
            "removed": "未连接",
            "none": "未扫描",
        }.get(row["status"], row["status"])
        sub = f"{status_text} · {row['total_files']:,} 个文件 · {format_size(row['total_size'])}"
        icon_kwargs = {}
        if self.disk_icon:
            icon_kwargs["image"] = self.disk_icon
        title_lbl = tk.Label(
            card, text=title, bg="#ffffff", fg="#1f2937", compound="left",
            font=("Microsoft YaHei UI", 10, "bold"), anchor="w",
            **icon_kwargs,
        )
        title_lbl.pack(fill="x")
        sub_lbl = tk.Label(
            card, text=sub, bg="#ffffff", fg="#64748b",
            font=("Microsoft YaHei UI", 9), anchor="w",
        )
        sub_lbl.pack(fill="x")
        card.title_lbl = title_lbl
        card.sub_lbl = sub_lbl
        disk_id = row["disk_id"]

        def on_click(_event=None, _disk_id=disk_id):
            self._select_disk(_disk_id)

        for widget in (card, title_lbl, sub_lbl):
            widget.bind("<Button-1>", on_click)

    def _select_disk(self, disk_id: str, refresh_tree: bool = True) -> None:
        self._selected_disk_id = disk_id
        self.current_disk = disk_id
        self.current_dir = ""
        self.search_mode = False
        for child in self.disk_cards.winfo_children():
            active = getattr(child, "disk_id", None) == disk_id
            bg = "#dbeafe" if active else "#ffffff"
            child.configure(bg=bg)
            child.title_lbl.configure(bg=bg)
            child.sub_lbl.configure(bg=bg)
        if refresh_tree:
            self.tree.delete(*self.tree.get_children())
            self._load_dir_nodes(disk_id, "", "")
        self._load_entries()
        self._update_stats()

    def _on_tree_select(self, _event=None) -> None:
        sel = self.tree.selection()
        if not sel:
            return
        kind, disk_id, path = _node_key(sel[0])
        if kind == "dir":
            self.current_disk = disk_id
            self.current_dir = path
            self.search_mode = False
            self._load_entries()

    def _on_tree_open(self, event) -> None:
        item = self.tree.focus()
        if not item:
            return
        kind, disk_id, path = _node_key(item)
        if kind != "dir":
            return
        children = self.tree.get_children(item)
        if children and self.tree.item(children[0], "tags") == ("dummy",):
            self.tree.delete(children[0])
        elif children:
            return
        self._load_dir_nodes(disk_id, path, item)

    def _load_dir_nodes(self, disk_id: str, parent: str, parent_iid: str) -> None:
        rows = self.conn.execute(
            "SELECT path, name FROM files WHERE disk_id=? AND parent=? AND is_dir=1 "
            "ORDER BY name COLLATE NOCASE",
            (disk_id, parent),
        ).fetchall()
        for row in rows:
            iid = _node_iid("dir", disk_id, row["path"])
            self.tree.insert(parent_iid, "end", iid=iid, text=row["name"])
            has_child = self.conn.execute(
                "SELECT 1 FROM files WHERE disk_id=? AND parent=? AND is_dir=1 LIMIT 1",
                (disk_id, row["path"]),
            ).fetchone()
            if has_child:
                self.tree.insert(iid, "end", text="...", tags=("dummy",))

    def _load_entries(self) -> None:
        self.table.delete(*self.table.get_children())
        if not self.current_disk:
            return
        disk_id = self.current_disk
        where = ["disk_id=?"]
        params: list = [disk_id]

        if not self.search_mode:
            where.append("parent=?")
            params.append(self.current_dir)
        else:
            keyword = self.search_var.get().strip()
            if keyword:
                where.append("(name LIKE ? OR path LIKE ?)")
                like = f"%{keyword}%"
                params.extend([like, like])

        ext = self.ext_var.get().strip().lower().lstrip(".")
        if ext:
            where.append("ext=?")
            params.append(ext)
        size_min = parse_size(self.size_min_var.get())
        if size_min is not None:
            where.append("size>=?")
            params.append(size_min)
        size_max = parse_size(self.size_max_var.get())
        if size_max is not None:
            where.append("size<=?")
            params.append(size_max)
        if self.date_from_var.get().strip():
            try:
                dt = datetime.strptime(self.date_from_var.get().strip(), "%Y-%m-%d")
                where.append("mtime>=?")
                params.append(int(dt.timestamp()))
            except ValueError:
                pass
        if self.date_to_var.get().strip():
            try:
                dt = datetime.strptime(self.date_to_var.get().strip() + " 23:59:59", "%Y-%m-%d %H:%M:%S")
                where.append("mtime<=?")
                params.append(int(dt.timestamp()))
            except ValueError:
                pass

        order_col = {
            "name": "name COLLATE NOCASE",
            "size": "size",
            "mtime": "mtime",
            "ext": "ext",
            "path": "path",
        }.get(self.sort_col, "name")
        order = "DESC" if self.sort_desc else "ASC"
        sql = (
            "SELECT path,name,is_dir,size,mtime,ext FROM files "
            f"WHERE {' AND '.join(where)} ORDER BY is_dir DESC, {order_col} {order} LIMIT 5000"
        )
        rows = self.conn.execute(sql, params).fetchall()
        for row in rows:
            iid = _node_iid("file", disk_id, row["path"])
            size = "-" if row["is_dir"] else format_size(row["size"])
            ext = "目录" if row["is_dir"] else (row["ext"] or "-")
            insert_kwargs = {
                "iid": iid,
                "text": row["name"],
                "values": (size, format_time(row["mtime"]), ext, row["path"]),
                "tags": ("dir",) if row["is_dir"] else (),
            }
            icon = self.folder_icon if row["is_dir"] else self.file_icon
            if icon:
                insert_kwargs["image"] = icon
            self.table.insert("", "end", **insert_kwargs)
        if len(rows) >= 5000:
            self.status_var.set("结果较多，仅显示前 5000 条；请使用搜索或筛选缩小范围")
        else:
            self.status_var.set("就绪")

    def _update_stats(self) -> None:
        if not self.current_disk:
            return
        row = db.get_disk(self.conn, self.current_disk)
        if row is None:
            self.stats_var.set("该硬盘索引已被删除")
            return
        name = row["label"].strip() or "未命名硬盘"
        serial = f" · 序列号 {row['volume_serial']}" if row["volume_serial"] else ""
        self.stats_var.set(
            f"{name}（{row['drive_letter'] or '未连接'}{serial}）· 文件 {row['total_files']:,} 个 · "
            f"总大小 {format_size(row['total_size'])} · 上次扫描 {format_time(row['last_scan_finished'])} · "
            f"上次新增 {row['last_added']} / 删除 {row['last_deleted']}"
        )

    def _sort_by(self, col: str) -> None:
        if self.sort_col == col:
            self.sort_desc = not self.sort_desc
        else:
            self.sort_col = col
            self.sort_desc = False
        self._load_entries()

    def _search(self) -> None:
        if not self.current_disk:
            return
        self.search_mode = True
        self._load_entries()

    def _clear_search(self) -> None:
        self.search_var.set("")
        self.ext_var.set("")
        self.size_min_var.set("")
        self.size_max_var.set("")
        self.date_from_var.set("")
        self.date_to_var.set("")
        self.search_mode = False
        self._load_entries()

    def _apply_filter(self) -> None:
        self._load_entries()

    def _on_table_double(self, event) -> None:
        item = self.table.identify_row(event.y)
        if not item:
            return
        kind, disk_id, path = _node_key(item)
        if kind != "file" or not self.current_disk:
            return
        row = self.conn.execute(
            "SELECT is_dir FROM files WHERE disk_id=? AND path=?",
            (self.current_disk, path),
        ).fetchone()
        if row and row["is_dir"]:
            target = _node_iid("dir", self.current_disk, path)
            self._reveal_dir(target, self.current_disk, path)

    def _reveal_dir(self, target_iid: str, disk_id: str, path: str) -> None:
        parts = path.split("/") if path else []
        cur = ""
        parent = ""
        parent_path = ""
        for part in parts:
            cur = f"{cur}/{part}" if cur else part
            iid = _node_iid("dir", disk_id, cur)
            if not self.tree.exists(iid):
                self._load_dir_nodes(disk_id, parent_path, parent)
            parent = iid
            parent_path = cur
        self.tree.item(parent, open=True)
        self.tree.see(target_iid)
        self.tree.selection_set(target_iid)
        self._on_tree_select()

    def _on_table_menu(self, event) -> None:
        item = self.table.identify_row(event.y)
        if not item:
            return
        self.table.selection_set(item)
        menu = tk.Menu(self, tearoff=0)
        menu.add_command(label="复制完整路径", command=lambda: self._copy_path(item))
        menu.tk_popup(event.x_root, event.y_root)

    def _copy_path(self, item: str) -> None:
        kind, disk_id, path = _node_key(item)
        if kind == "file" and self.current_disk:
            text = path
            row = db.get_disk(self.conn, self.current_disk)
            if row and row["drive_letter"]:
                text = f"{row['drive_letter'].rstrip('\\\\')}\\{path.replace('/', '\\\\')}"
            self.clipboard_clear()
            self.clipboard_append(text)

    # ---------------- actions ----------------

    def rescan_current(self) -> None:
        if not self.current_disk:
            messagebox.showinfo("提示", "请先在左侧选择一块硬盘")
            return
        if not messagebox.askyesno("重新扫描", "将重新完整扫描这块硬盘（只读，不修改盘上文件），继续吗？"):
            return
        from .single_instance import SingleInstance
        from .scanner import scan_disk

        disk_id = self.current_disk
        db.request_scan(self.conn, disk_id, "full")
        if SingleInstance.is_running("CatalogExporterV2Tray"):
            self.status_var.set("已加入完整扫描队列")
        else:
            self.status_var.set("正在完整扫描…")
            threading.Thread(
                target=scan_disk,
                kwargs={"disk_id": disk_id, "mode": "full", "db_path": self.db_path},
                daemon=True,
            ).start()
        self.refresh_disks()

    def export_current(self) -> None:
        if not self.current_disk:
            messagebox.showinfo("提示", "请先选择一块硬盘")
            return
        disk = db.get_disk(self.conn, self.current_disk)
        if disk is None:
            return
        serial = disk["volume_serial"] or ""
        base = safe_filename(disk["label"].strip() or f"{disk['drive_letter'].replace(':', '')}_{serial}")
        default = f"DiskMenu_{base}_{datetime.now():%Y%m%d_%H%M}.html"
        path = filedialog.asksaveasfilename(
            title="导出为 HTML 离线报告",
            defaultextension=".html",
            initialfile=default,
            filetypes=[("HTML 文件", "*.html")],
        )
        if not path:
            return
        disk_id = self.current_disk
        self.status_var.set("正在导出…")
        self.config(cursor="watch")

        def work():
            ok, msg = export_html(self.db_path, disk_id, path)
            self.after(0, lambda: self._export_done(ok, msg, path))

        threading.Thread(target=work, daemon=True).start()

    def _export_done(self, ok: bool, msg: str, path: str) -> None:
        self.config(cursor="")
        if ok:
            self.status_var.set("导出完成")
            if messagebox.askyesno("导出完成", f"已导出到：\n{msg}\n\n是否立即打开？"):
                os.startfile(msg)  # type: ignore[attr-defined]
        else:
            messagebox.showerror("导出失败", msg)
            self.status_var.set("导出失败")

    def delete_current(self) -> None:
        if not self.current_disk:
            return
        if messagebox.askyesno("删除索引", "将删除这块硬盘的全部索引，之后如需浏览需重新插盘扫描。确定？"):
            db.delete_disk_index(self.conn, self.current_disk)
            self.refresh_disks()
            self.status_var.set("索引已删除")

    def clear_all(self) -> None:
        if messagebox.askyesno("清空全部索引", "将清空所有硬盘的索引记录，确定？"):
            db.clear_all_indexes(self.conn)
            self.refresh_disks()
            self.status_var.set("已清空全部索引")

    # ---------------- settings ----------------

    def open_settings(self) -> None:
        win = tk.Toplevel(self)
        win.title("设置")
        win.geometry("500x640")
        win.resizable(False, False)
        win.transient(self)
        settings = db.get_settings(self.conn)

        canvas = tk.Canvas(win, bg="#f3f6fb", highlightthickness=0)
        vsb = ttk.Scrollbar(win, orient="vertical", style="Modern.Vertical.TScrollbar", command=canvas.yview)
        canvas.configure(yscrollcommand=vsb.set)
        canvas.pack(side="left", fill="both", expand=True)
        vsb.pack(side="right", fill="y")
        frame = ttk.Frame(canvas, padding=14)
        frame_id = canvas.create_window((0, 0), window=frame, anchor="nw")

        def _on_frame_config(_event=None):
            canvas.configure(scrollregion=canvas.bbox("all"))
            canvas.itemconfigure(frame_id, width=canvas.winfo_width())

        frame.bind("<Configure>", _on_frame_config)
        canvas.bind("<Configure>", _on_frame_config)
        win.bind("<MouseWheel>", lambda e: canvas.yview_scroll(int(-e.delta / 120), "units"))
        self._start_var = tk.BooleanVar(value=settings.get("start_at_login", "0") == "1")
        self._hidden_var = tk.BooleanVar(value=settings.get("scan_hidden", "0") == "1")
        self._system_var = tk.BooleanVar(value=settings.get("scan_system", "0") == "1")
        self._removable_var = tk.BooleanVar(value=settings.get("scan_removable", "1") == "1")
        self._fixed_var = tk.BooleanVar(value=settings.get("scan_fixed_new", "1") == "1")
        self._ignore_var = tk.StringVar(value=settings.get("ignore_drives", ""))
        self._extra_var = tk.StringVar(value=settings.get("extra_external", ""))
        self._pwd_var = tk.StringVar()
        self._auto_boot_var = tk.BooleanVar(value=settings.get("auto_export_on_boot", "0") == "1")
        self._auto_insert_var = tk.BooleanVar(value=settings.get("auto_export_on_insert", "0") == "1")
        self._auto_dir_var = tk.StringVar(value=settings.get("auto_export_dir", ""))

        ttk.Checkbutton(frame, text="开机自动启动（后台托盘运行）", variable=self._start_var).pack(anchor="w")
        ttk.Checkbutton(frame, text="扫描隐藏文件（默认关闭）", variable=self._hidden_var).pack(anchor="w", pady=(8, 0))
        ttk.Checkbutton(frame, text="扫描系统文件（默认关闭）", variable=self._system_var).pack(anchor="w")
        ttk.Checkbutton(frame, text="自动扫描可移动盘（U 盘等）", variable=self._removable_var).pack(anchor="w", pady=(8, 0))
        ttk.Checkbutton(frame, text="自动扫描固定盘（含本地硬盘、USB 硬盘盒）", variable=self._fixed_var).pack(anchor="w")
        ttk.Label(frame, text="忽略的盘符（如 D:,E:，逗号分隔）").pack(anchor="w", pady=(10, 2))
        ttk.Entry(frame, textvariable=self._ignore_var).pack(fill="x")
        ttk.Label(frame, text="强制视为外接盘的盘符（可选）").pack(anchor="w", pady=(10, 2))
        ttk.Entry(frame, textvariable=self._extra_var).pack(fill="x")
        ttk.Separator(frame).pack(fill="x", pady=12)
        ttk.Label(frame, text="自动导出 HTML 报告", font=("Microsoft YaHei", 10, "bold")).pack(anchor="w")
        ttk.Checkbutton(frame, text="开机时自动导出所有已索引硬盘的报告", variable=self._auto_boot_var).pack(anchor="w", pady=(6, 0))
        ttk.Checkbutton(frame, text="插入硬盘并扫描完成后自动导出该硬盘的报告", variable=self._auto_insert_var).pack(anchor="w", pady=(4, 0))
        dir_row = ttk.Frame(frame)
        dir_row.pack(fill="x", pady=(8, 0))
        self._auto_dir_entry = ttk.Entry(dir_row, textvariable=self._auto_dir_var)
        self._auto_dir_entry.pack(side="left", fill="x", expand=True, padx=(0, 6))
        ttk.Button(dir_row, text="选择文件夹", command=self._choose_auto_dir).pack(side="right")
        ttk.Label(frame, text="导出目录不存在时会自动创建；每块盘按“盘符盘_usb_序列号”保存到子文件夹（检测到 USB 时带 usb），如 i盘_usb_6e42646d。", foreground="#888").pack(anchor="w", pady=(3, 0))
        ttk.Separator(frame).pack(fill="x", pady=12)
        ttk.Label(frame, text="索引密码保护（可选，留空表示不修改）").pack(anchor="w", pady=(0, 2))
        ttk.Entry(frame, textvariable=self._pwd_var, show="*").pack(fill="x")
        ttk.Label(frame, text="提示：设置密码后，打开主界面需要输入密码。", foreground="#888").pack(anchor="w", pady=(4, 0))

        def save():
            from . import autostart

            values = {
                "start_at_login": "1" if self._start_var.get() else "0",
                "scan_hidden": "1" if self._hidden_var.get() else "0",
                "scan_system": "1" if self._system_var.get() else "0",
                "scan_removable": "1" if self._removable_var.get() else "0",
                "scan_fixed_new": "1" if self._fixed_var.get() else "0",
                "ignore_drives": self._ignore_var.get().strip(),
                "extra_external": self._extra_var.get().strip(),
                "auto_export_on_boot": "1" if self._auto_boot_var.get() else "0",
                "auto_export_on_insert": "1" if self._auto_insert_var.get() else "0",
                "auto_export_dir": self._auto_dir_var.get().strip(),
            }
            if (values["auto_export_on_boot"] == "1" or values["auto_export_on_insert"] == "1") and not values["auto_export_dir"]:
                messagebox.showwarning("提示", "请先选择自动导出的文件夹", parent=win)
                return
            pwd = self._pwd_var.get()
            if pwd:
                values["password_hash"] = _hash_password(pwd)
            db.set_settings_many(self.conn, values)
            self.settings = db.get_settings(self.conn)
            try:
                if values["start_at_login"] == "1":
                    autostart.install()
                    if not autostart.is_installed():
                        messagebox.showwarning("开机自启", "开机自启可能未生效，请检查杀毒软件或权限设置。", parent=win)
                else:
                    autostart.uninstall()
            except Exception as exc:
                messagebox.showwarning("开机自启", f"设置开机自启失败：{exc}", parent=win)
            win.destroy()
            self.status_var.set("设置已保存")

        RoundedButton(frame, text="保存", command=save, canvas_bg="#f3f6fb").pack(pady=12)

    def _choose_auto_dir(self) -> None:
        start = self._auto_dir_var.get().strip() or None
        chosen = filedialog.askdirectory(title="选择自动导出文件夹", initialdir=start, parent=self)
        if chosen:
            self._auto_dir_var.set(chosen)

    # ---------------- status / close ----------------

    def _poll_status(self) -> None:
        try:
            rows = db.list_disks(self.conn)
            scanning = [r for r in rows if r["status"] in ("scanning", "queued")]
            ids = {r["disk_id"] for r in rows}
            if ids != self._known_disk_ids:
                self.refresh_disks()
            if scanning:
                r = scanning[0]
                name = r["label"].strip() or r["drive_letter"] or "硬盘"
                self.status_var.set(
                    f"{name} 扫描中：已处理 {r['scan_processed']} 个目录，当前 {r['scan_current'] or '…'}"
                )
            elif self.status_var.get().startswith("扫描") or self.status_var.get() in ("就绪",):
                self.status_var.set("就绪")
            self._update_stats()
        except Exception:
            pass
        self.after(2000, self._poll_status)

    def _on_close(self) -> None:
        try:
            self.conn.close()
        finally:
            self.destroy()


def run(db_path: Optional[str] = None) -> None:
    _enable_dpi_awareness()
    app = MainWindow(db_path)
    try:
        if app.winfo_exists():
            app.mainloop()
    except tk.TclError:
        pass
