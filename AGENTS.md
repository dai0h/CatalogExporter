# CatalogExporter v1.3 交接说明（给 AI 助手）

> 本文件是给任何接手本项目的 GPT / Codex 助手的“项目说明书”。请先读完再动手。

## 1. 项目是什么

CatalogExporter（目录导出管家）是 Windows 便携软件：插入外接硬盘后自动扫描并记录完整文件目录，拔盘后仍可离线浏览、搜索、筛选，并可导出单文件 HTML 目录报告。开源仓库：https://github.com/dai0h/CatalogExporter

当前版本 **v1.3.0**：界面层已用 **PySide6（Qt for Python）** 重构，业务逻辑与 v1.2 完全一致。

## 2. 铁律：业务层禁止改动

以下文件是 v1.2 原样保留的业务层，**接口和行为不得修改**：

```
diskmenu/db.py        SQLite 数据层
diskmenu/scanner.py   只读扫描器（增量/断点续扫）
diskmenu/volumes.py   Windows 卷枚举与 USB 识别
diskmenu/service.py   后台服务与自动导出
diskmenu/exporter.py  HTML 离线报告生成（内含 52KB 新模板）
diskmenu/cli.py       命令行（list/scan/export/delete/clear/install/uninstall/gui/tray）
diskmenu/autostart.py 开机自启（注册表）
diskmenu/single_instance.py / paths.py / util.py
main.py / run_gui.pyw / run_tray.pyw
```

命令行行为、隐私边界（只读扫描、数据仅存本机）不得改变。

## 3. v1.3 改了什么（界面/集成层）

- `diskmenu/gui.py`：Tkinter 主窗口 → PySide6 QMainWindow（左侧硬盘卡片+懒加载目录树，右侧 QTableView + 排序/过滤代理模型）
- `diskmenu/tray.py`：ctypes 托盘 → QSystemTrayIcon（菜单：打开主界面/开始或停止扫描/导出报告/退出；保留 WM_DEVICECHANGE 监听）
- `diskmenu/entry.py`：适配 Qt 事件循环并接线托盘通知
- 新增：`qt_theme.py`（浅/深色 QSS）、`qt_models.py`（FileTableModel/FileFilterProxyModel）、`qt_widgets.py`（DiskCardWidget/DirTreeWidget）、`settings_dialog.py`
- 新增：`assets/icons/*.svg`；`tests/test_qt.py`；`requirements*.txt` 增加 PySide6

## 4. 运行与测试（源码）

```bat
python -m unittest discover -s tests -v        :: 12 个测试（核心 4 + Qt 8）
python main.py gui                             :: 图形界面
python main.py tray                            :: 托盘后台
python main.py list                            :: CLI
```

环境要求：Windows 10/11，Python 3.10+，已安装 PySide6（本机 Python314 系统 site-packages 已装 PySide6-Essentials 6.11.1 + PyInstaller 6.22）。

## 5. 打包（重要：本机有沙盒特殊性）

**不要直接跑 `python -m PyInstaller`**。本机规则把该前缀放行到沙盒外，而沙盒外进程读不到沙盒内安装的 PySide6，会打出没有 Qt 的坏包。

正确做法（沙盒内执行，输出到全新目录，避免旧产物权限锁）：

```bat
set PYINSTALLER_CONFIG_DIR=F:\codex\disk-menu\.pyinstaller\config
python -c "from PyInstaller.__main__ import run; run(['--noconfirm','--clean','--distpath','F:\\codex\\disk-menu\\build_tools\\v1.3_dist','--workpath','F:\\codex\\disk-menu\\build_tools\\v1.3_build','CatalogExporter.spec'])"
```

打包后校验：`distpath\_internal\PySide6\plugins\platforms\qwindows.dll` 必须存在。

已知坑：
- `CatalogExporter-v1.3\dist` 与 `build` 是旧产物，被沙盒账户锁住，删除需要管理员（takeown）；**不要尝试在打包时原地覆盖**，一律用新的 `--distpath/--workpath`。
- 提权（require_escalated）下 `import PySide6.QtWidgets` 会失败（ACL 隔离），属正常现象；沙盒内正常。
- 修改 `qt_theme.py` 的 QSS 后必须重新打包才生效；改前先用 offscreen 渲染截图自查（`QT_QPA_PLATFORM=offscreen` + `w.grab().save(...)`）。

## 6. 本机环境事实（2026-08-14）

- 用户级与系统级各有一份 PyInstaller；沙盒内可见的是系统级 `C:\Users\daihe\AppData\Local\Programs\Python\Python314\Lib\site-packages\PyInstaller`
- PySide6 装在系统 site-packages（沙盒内安装，权限正确）
- `C:\Users\daihe\.codex\rules\default.rules`：白名单规则（python.exe -m PyInstaller 自动放行）
- `C:\Users\daihe\.codex\config.toml`：`sandbox_mode=workspace-write`，writable_roots 含 Python314
- 这些规则是用户级全局的，**本机任何 Codex 会话（包括新会话）都生效**

## 7. 工作约定

- 改动界面时保持功能等价；删功能前先说明理由和方案
- 每个界面改动后用 offscreen 渲染验证外观（浅色+深色），并运行全部测试
- 大改动更新 README.md 的“项目结构/迁移说明”
- 不要修改业务层文件；确需扩展接口时先与用户确认
