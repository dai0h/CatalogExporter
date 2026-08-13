@echo off
chcp 65001 >nul
cd /d "%~dp0"
echo 正在安装 PyInstaller（首次需要联网）...
python -m pip install -r requirements-build.txt
if errorlevel 1 goto :fail
echo 正在打包...
python -m PyInstaller --noconfirm --clean --onedir --windowed --name CatalogExporter ^
  --icon assets\icon.ico --add-data "assets;assets" main.py
if errorlevel 1 goto :fail
echo.
echo 打包完成：dist\CatalogExporter\CatalogExporter.exe
echo 请把整个 CatalogExporter 文件夹放到固定目录，然后运行 CatalogExporter\CatalogExporter.exe install 设置开机自启。
pause
exit /b 0
:fail
echo 打包失败，请检查错误信息。
pause
exit /b 1
