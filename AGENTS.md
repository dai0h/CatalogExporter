# CatalogExporter v1.3 项目交接说明

> 本文件是项目交接说明，供后续开发者维护时参考。请先读完再动手。

## 1. 项目是什么

CatalogExporter（目录导出管家）是 Windows 便携软件：插入外接硬盘后自动扫描并记录完整文件目录，拔盘后仍可离线浏览、搜索、筛选，并可导出单文件 HTML 目录报告。

当前版本 **v1.3.0**：界面层基于 **PySide6（Qt for Python）**，业务逻辑与 v1.2 完全一致。

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

- `diskmenu/gui.py`：主窗口（左侧硬盘卡片 + 懒加载目录树，右侧表格 + 排序/过滤代理模型）
- `diskmenu/tray.py`：系统托盘（菜单：打开主界面 / 开始或停止扫描 / 导出报告 / 退出；保留设备变化监听）
- `diskmenu/entry.py`：适配事件循环并接线托盘通知
- 新增：`qt_theme.py`（浅/深色 QSS）、`qt_models.py`（表格模型/代理模型）、`qt_widgets.py`（硬盘卡片/目录树）、`settings_dialog.py`
- 新增：`assets/icons/*.svg`；`tests/test_qt.py`；`requirements*.txt` 增加 PySide6

## 4. 运行与测试（源码）

```bat
python -m unittest discover -s tests -v        :: 12 个测试（核心 4 + Qt 8）
python main.py gui                             :: 图形界面
python main.py tray                            :: 托盘后台
python main.py list                            :: CLI
```

环境要求：Windows 10/11，Python 3.10+，已安装 PySide6。

## 5. 打包（PyInstaller）

推荐使用项目内 `CatalogExporter.spec` 打包，输出到全新目录，避免旧产物被占用：

```bat
set PYINSTALLER_CONFIG_DIR=<项目目录>\.pyinstaller\config
python -c "from PyInstaller.__main__ import run; run(['--noconfirm','--clean','--distpath','<项目目录>\\build_tools\\v1.3_dist','--workpath','<项目目录>\\build_tools\\v1.3_build','CatalogExporter.spec'])"
```

打包后校验：`<输出目录>\_internal\PySide6\plugins\platforms\qwindows.dll` 必须存在。

已知坑：
- `dist` 与 `build` 可能是旧的构建产物，若被权限锁定，不要原地覆盖，一律使用新的 `--distpath/--workpath`。
- 修改 `qt_theme.py` 的 QSS 后必须重新打包才生效；改前用离屏渲染截图自查（`QT_QPA_PLATFORM=offscreen` + `w.grab().save(...)`）。
- 本机若存在多个 Python 环境，请确认打包所用 Python 能正常 `import PySide6`。

## 6. 工作约定

- 改动界面时保持功能等价；删功能前先说明理由和方案
- 每个界面改动后用离屏渲染验证外观（浅色 + 深色），并运行全部测试
- 大改动更新 README.md 的“项目结构 / 迁移说明”
- 不要修改业务层文件；确需扩展接口时先与用户确认
