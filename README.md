# CatalogExporter · 目录导出管家

> 插盘自动扫描 · 拔盘离线浏览 · 一键导出 HTML 目录报告

CatalogExporter 是一款面向普通用户的 Windows 便携软件：插入外接硬盘后自动扫描并记录完整文件目录，拔下硬盘后依然可以像“查目录”一样浏览、搜索、筛选硬盘里的文件，并随时导出一份自带搜索、排序和目录树的 HTML 离线报告。

本项目使用 Python 标准库（tkinter + sqlite3 + ctypes）开发，无第三方运行时依赖，可打包为免安装便携版。

---

## 功能特性

- **插盘全自动扫描**：后台常驻托盘，检测到硬盘插入后立即自动扫描，无需打开软件、无需点击任何按钮
- **稳定硬盘识别**：使用卷 GUID / 卷序列号区分硬盘，不依赖盘符；多块硬盘索引互不混淆
- **增量与续扫**：再次插入同一块硬盘自动更新；扫描中拔盘安全中止，下次插入自动续扫
- **拔盘离线浏览**：左侧硬盘卡片 + 目录树，右侧文件列表，支持搜索、排序、类型/大小/日期筛选
- **HTML 离线报告**：单文件、无需联网，自带目录树、查看方式切换（详细信息/列表/内容/平铺/大小图标）、列宽与区域拖拽调整
- **自动导出**：可设置开机自动导出、插盘扫描完成后自动导出，按“盘符盘_usb_序列号”分文件夹保存
- **容量可视化**：报告顶部显示总容量、已用空间与图形化进度条
- **隐私安全**：索引仅保存在本机，只读扫描，不上传任何数据
- **命令行支持**：`list` / `scan` / `export` / `delete` / `clear` / `install` / `uninstall`

---

## 快速开始

### 源码运行

环境要求：Windows 10/11，Python 3.10+（安装时勾选 Add Python to PATH）。

```bat
python main.py gui     :: 打开图形界面
python main.py tray    :: 启动后台托盘服务
python main.py install :: 设置开机自启
```

### 便携版

直接下载 Release 中的 `CatalogExporter_便携版.zip`，解压后双击 `CatalogExporter\CatalogExporter.exe` 即可运行，无需安装 Python。

---

## 命令行示例

```bat
python main.py list
python main.py scan --disk <disk_id> --full
python main.py export --disk <disk_id> --out D:\report.html
python main.py delete --disk <disk_id>
python main.py clear
```

`list` 会输出硬盘 ID（卷 GUID）、盘符、序列号、状态、文件数与总大小。

---

## 自动导出规则

在“设置 → 自动导出 HTML 报告”中可配置：

- 开机时自动导出所有已索引硬盘的报告
- 插入硬盘并扫描完成后自动导出该硬盘的报告
- 导出目录按“盘符盘_usb_序列号”分子文件夹保存

例如：

```text
导出目录/
├── c盘_6eb6916a/
│   └── C盘_6eb6916a_20260813_180000.html
├── i盘_usb_6e42646d/
│   └── I盘_usb_6e42646d_20260813_180000.html
```

USB 识别基于 Windows 物理磁盘 `BusType`，不会把 M.2/NVMe 误判为 USB。

---

## 项目结构

```text
CatalogExporter/
├── main.py                  # 命令行 / 启动入口
├── run_gui.pyw              # 图形界面入口
├── run_tray.pyw             # 托盘后台入口
├── diskmenu/
│   ├── db.py                # SQLite 数据层
│   ├── scanner.py           # 只读扫描器（增量/断点续扫）
│   ├── volumes.py           # Windows 卷枚举与 USB 识别
│   ├── service.py           # 后台服务与自动导出
│   ├── tray.py              # 系统托盘（ctypes）
│   ├── gui.py               # Tkinter 主界面
│   ├── exporter.py          # HTML 离线报告生成
│   ├── cli.py               # 命令行工具
│   ├── autostart.py         # 开机自启（注册表 + 启动文件夹）
│   └── ...
├── assets/                  # 图标资源
├── tests/                   # 自动化测试
└── build_exe.bat            # PyInstaller 打包脚本
```

---

## 构建与测试

```bat
:: 运行测试
python -m unittest discover -s tests -v

:: 打包便携版（需安装 PyInstaller）
python -m pip install -r requirements-build.txt
build_exe.bat
```

打包产物位于 `dist\CatalogExporter\`。

---

## 隐私说明

- 软件只记录文件目录信息（路径、名称、大小、修改时间），不读取文件内容
- 索引数据库保存在本机 `%APPDATA%\DiskMenu\index.db`
- 导出的 HTML 报告同样只包含目录信息，可放心拷贝、发送

---

## 开源协议

本项目基于 [MIT License](LICENSE) 开源，欢迎使用、修改和二次开发。

> 本项目由开发者与 AI 编程助手（Codex）协作完成。
