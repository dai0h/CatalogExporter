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

## 7. README 预览图生成方式

README 的「界面预览」一节共 5 张图，全部放在仓库根目录 `assets/` 下，用相对路径引用（如 `assets/ui_light.png`），GitHub 会自动渲染：

| 文件 | 内容 |
|---|---|
| `assets/ui_light.png` | 软件主界面 · 浅色主题（约 1180×720） |
| `assets/ui_dark.png` | 软件主界面 · 深色主题（约 1180×720） |
| `assets/ui_settings_light.png` | 设置对话框 · 浅色（约 520×620） |
| `assets/ui_settings_dark.png` | 设置对话框 · 深色（约 520×620） |
| `assets/screenshot_html_v2.png` | 导出的 HTML 目录报告（演示数据） |

生成步骤（源码运行，Windows 桌面环境）：

1. 运行 `python main.py gui` 打开主窗口，先切浅色主题截主界面，再切深色主题截一张。画面需包含左侧硬盘卡片 + 目录树、右侧文件列表，并保证列表中有真实数据，不要空白列表。
2. 在主界面打开「设置」对话框，浅色/深色各截一张。
3. HTML 报告截图：用演示数据执行 `python main.py export --disk <disk_id> --out report.html`，用浏览器打开导出的报告后截图（画面需含目录树与文件列表）。
4. 没有显示器时可离屏渲染：设 `QT_QPA_PLATFORM=offscreen` 后用 `window.grab().save('assets/ui_light.png')` 保存主界面，设置对话框同理（`settings_dialog.grab().save(...)`）。

注意事项：

- 浅色/深色必须成对提供；截图内不要出现突兀的纯黑（圆角缺口、分割线要使用主题色）。
- 文件名保持稳定（`ui_light.png` / `ui_dark.png` / `ui_settings_light.png` / `ui_settings_dark.png`）；截图内容有实质变化时改用新文件名（如 `ui_light_v2.png`）并同步更新 README，否则 GitHub 图片缓存会继续显示旧图。
- 新增或替换截图后，运行第 4 节的全部测试，并在本地打开 README 确认图片路径正确。

## 8. GitHub 上传要领

### 8.1 常规约定

- 远程仓库：`https://github.com/dai0h/CatalogExporter`，主分支 `main`。
- README 图片必须放在仓库内 `assets/` 并用相对路径引用，不要外链图床。
- Release 附件命名：`CatalogExporter_v<版本>_portable.zip`（如 `CatalogExporter_v1.3.0_portable.zip`）；tag 用 `v<版本>`（如 `v1.3.0`）。
- 公开内容不要出现“AI 编程助手 / Codex”等标识；旧 Release 说明里残留的此类文字也要清理。
- 提交后 `git status` 应干净，本地 main 与 origin/main 指向同一 commit。

### 8.2 网络受限时的 API 推送（重要）

现象：`git push` 报 `Failed to connect to github.com:443` 或长时间超时，但 `api.github.com` 可正常访问。这是 github.com 域名被网络层间歇性重置（TLS/SNI 层拦截），改 IP、改 hosts、换备用 IP 都无效；此时改用 Git Data API 推送。

1. 先重试普通 `git push origin main`；确认 `curl https://api.github.com` 通、`curl https://github.com` 不通后再走 API。
2. 取凭据（只保留在内存中，禁止打印、禁止写入文件或提交）：
   - 管道输入 `protocol=https` + `host=github.com` 给 `git credential fill`，取返回的 `password=` 作为 Bearer token。
3. 按顺序调用（URL 前缀 `https://api.github.com/repos/dai0h/CatalogExporter`，需带 `Authorization: Bearer <token>`）：
   - `POST /git/blobs`：变更文件内容用 base64 上传（`encoding: base64`）；返回 sha 必须等于本地 `git hash-object <文件>` 的结果。
   - `POST /git/trees`：`base_tree` 填当前远端 main 的 tree sha，`tree` 填变更条目（`path` / `mode: 100644` / `type: blob` / `sha`）；返回 sha 必须等于本地新 commit 的 tree sha。
   - `POST /git/commits`：`tree`、`parents`、`author/committer`（name/email/date 与本地一致，date 用 ISO8601 并保留时区）；注意 GitHub 存储的 commit 消息没有尾部换行，所以远端 sha 与本地普通 `git commit` 的 sha 不同，属正常现象。
   - `PATCH /git/refs/heads/main`：`{"sha": <上一步 sha>, "force": false}`（必须 fast-forward）。
4. 把本地仓库对齐到远端 sha：
   - 用 `git cat-file commit <本地sha>` 取 tree/parent/author/committer/message。
   - 按远端序列化（消息无尾换行）重建 commit 对象：`git hash-object -t commit -w <文件>`，校验 sha 与远端一致。
   - `git update-ref refs/heads/main <远端sha>` 与 `git update-ref refs/remotes/origin/main <远端sha>`。
   - 若其他本地副本缺少 tree/blob 对象：用 `git rev-list --objects <sha>` 列出对象，从已有仓库拷贝 `.git/objects/xx/yyyy...`（或 `git cat-file` 导出后用 `git hash-object -t <type> -w` 写回），最后 `git fsck --connectivity-only` 校验。
5. 校验：`GET /git/ref/heads/main` 确认 sha；`GET /contents/<路径>` 确认文件内容哈希与本地一致。
6. Release：`POST /releases` 创建（`tag_name` / `target_commitish` / `name` / `body`），再用 `POST https://uploads.github.com/repos/dai0h/CatalogExporter/releases/{id}/assets?name=...` 上传附件（Content-Type: application/zip）。
