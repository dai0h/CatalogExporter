@echo off
chcp 65001 >nul
cd /d "%~dp0"
set "PYTHON_EXE=C:\Users\daihe\AppData\Local\Programs\Python\Python314\python.exe"
if not exist "%PYTHON_EXE%" (
  echo 未找到 Python 3.14：%PYTHON_EXE%
  echo 请确认 Python 安装路径，或手动修改本文件中的 PYTHON_EXE。
  pause
  exit /b 1
)
echo 正在安装 PyInstaller（首次需要联网）...
"%PYTHON_EXE%" -m pip install -r requirements-build.txt
if errorlevel 1 goto :fail
echo 正在打包...
"%PYTHON_EXE%" -m PyInstaller --noconfirm --clean --onedir --windowed --name CatalogExporter ^
  --icon assets\icon.ico --add-data "assets;assets" ^
  --hidden-import diskmenu.gui ^
  --hidden-import diskmenu.tray ^
  --hidden-import tkinter ^
  --hidden-import tkinter.filedialog ^
  --hidden-import tkinter.messagebox ^
  --hidden-import tkinter.ttk ^
  main.py
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
