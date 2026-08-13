# CatalogExporter 目录导出管家

插入外接硬盘时自动扫描并记录完整文件目录；拔盘后仍可像“查目录”一样浏览、搜索、排序、筛选硬盘里的文件。索引只保存在本机，不会上传任何数据。

## 功能

- 后台托盘常驻，插入硬盘后全自动扫描，无需打开软件或点击任何按钮
- 用卷 GUID / 卷序列号识别硬盘，不依赖盘符；多块硬盘索引互不混淆
- 再次插入同一块硬盘自动增量更新；扫描中断后下次插入自动续扫
- 拔盘后离线浏览：目录树 + 文件列表，按名称/大小/时间排序，关键字搜索，类型/大小/日期筛选
- 每块硬盘显示文件总数、总大小、最近扫描时间、本次新增/删除数量
- 一键导出单个 HTML 离线报告，自带目录树、搜索、排序、筛选和分页，双击即可在任何设备上查看
- 可选：开机自动导出所有硬盘报告、插入硬盘扫描完成后自动导出，保存到指定文件夹
- 命令行工具：`list`、`scan`、`export`、`delete`、`clear`
- 只读扫描，绝不修改硬盘内容；权限不足或坏道目录会跳过并记录

## 环境要求

- Windows 10/11
- Python 3.10 或更高（安装时勾选 **Add Python to PATH**）
- 无需任何第三方 Python 包

## 快速开始（源码运行）

1. 推荐双击 `安装到电脑.bat`：它会复制程序到 `%LOCALAPPDATA%\CatalogExporterApp`、设置开机自启并启动托盘服务。
2. 也可以双击 `启动后台服务.bat`，程序会在系统托盘运行。
3. 右键托盘图标 → “打开主界面”浏览索引；双击托盘图标也会打开主界面。
4. 在“设置”中勾选“开机自动启动”，以后开机自动驻留后台。

也可以直接运行：

```bat
python main.py gui
python main.py tray
```

## 命令行示例

```bat
python main.py list
python main.py scan --disk <disk_id> --full
python main.py export --disk <disk_id> --out D:\report.html
python main.py delete --disk <disk_id>
python main.py clear
```

`list` 输出中的第一列（卷 GUID）就是 `<disk_id>`。

## 打包成 exe（可选）

双击 `build_exe.bat`，生成 `dist\CatalogExporter\CatalogExporter.exe`（文件夹模式，避免单文件版的临时目录清理报错）。该命令需要联网安装 PyInstaller。

## 数据位置

索引数据库位于 `%APPDATA%\DiskMenu\index.db`。删除 `%APPDATA%\DiskMenu` 即可彻底清除全部数据。

## 常见问题

见 `使用说明.md`。
