@echo off
chcp 65001 >nul
cd /d "%~dp0"
echo 请先右键系统托盘中的“目录导出管家”图标并选择“退出”，再继续。
pause
where python >nul 2>nul
if errorlevel 1 (
  echo 未找到 Python。请手动删除开机启动项“CatalogExporter”：
  echo 按 Win+R 输入 regedit，进入 HKEY_CURRENT_USER\Software\Microsoft\Windows\CurrentVersion\Run，
  echo 删除名为 CatalogExporter 的值。
) else (
  python main.py uninstall
  echo 已取消开机自启。
)
echo.
echo 如需彻底删除索引数据，请手动删除 %APPDATA%\DiskMenu 文件夹。
pause
