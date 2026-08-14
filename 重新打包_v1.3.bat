@echo off
chcp 65001 >nul
cd /d "%~dp0"

set "PYTHON_EXE=C:\Users\daihe\AppData\Local\Programs\Python\Python314\python.exe"

echo.
echo  目录导出管家 v1.3 重新打包（PySide6）
echo  使用 Python：%PYTHON_EXE%
echo.

if not exist "%PYTHON_EXE%" (
  echo [失败] 未找到 Python 3.14。
  echo 请确认路径是否存在，或编辑本文件中的 PYTHON_EXE。
  pause
  exit /b 1
)

echo 正在关闭旧的 CatalogExporter 进程 ...
taskkill /f /t /im CatalogExporter.exe >nul 2>nul
timeout /t 1 /nobreak >nul

if exist "dist\CatalogExporter" (
  echo 正在删除旧的 dist\CatalogExporter ...
  attrib -r -s -h "dist\CatalogExporter" /s /d >nul 2>nul
  rmdir /s /q "dist\CatalogExporter"
  if exist "dist\CatalogExporter" (
    echo [失败] 无法删除旧的 dist\CatalogExporter。
    echo 请关闭 CatalogExporter、退出托盘图标，并关闭正在浏览该目录的资源管理器窗口后重试。
    pause
    exit /b 1
  )
)

echo 正在确认 PySide6 ...
"%PYTHON_EXE%" -c "import PySide6; print('PySide6 OK', PySide6.__version__)"
if errorlevel 1 goto :fail

echo 正在确认 PyInstaller ...
"%PYTHON_EXE%" -m PyInstaller --version
if errorlevel 1 (
  echo 正在安装 PyInstaller ...
  "%PYTHON_EXE%" -m pip install -r requirements-build.txt
  if errorlevel 1 goto :fail
)

echo 正在打包 v1.3 ...
"%PYTHON_EXE%" -m PyInstaller --noconfirm --clean --onedir --windowed --name CatalogExporter ^
  --icon assets\icon.ico --add-data "assets;assets" ^
  --hidden-import diskmenu.gui ^
  --hidden-import diskmenu.tray ^
  --hidden-import diskmenu.qt_models ^
  --hidden-import diskmenu.qt_widgets ^
  --hidden-import diskmenu.qt_theme ^
  --hidden-import diskmenu.settings_dialog ^
  main.py
if errorlevel 1 goto :fail

if not exist "dist\CatalogExporter\_internal\PySide6" (
  echo [失败] 打包完成但缺少 PySide6 运行时，界面无法启动。
  pause
  exit /b 1
)
if not exist "dist\CatalogExporter\_internal\PySide6\plugins\platforms\qwindows.dll" (
  echo [失败] 缺少 Qt Windows 平台插件 qwindows.dll。
  pause
  exit /b 1
)

echo.
echo [成功] v1.3 便携版已生成：
echo %cd%\dist\CatalogExporter\CatalogExporter.exe
echo.
echo 请运行上面这个 exe，不要运行旧版本里的 exe。
pause
exit /b 0

:fail
echo.
echo [失败] 打包未完成，请查看上方错误信息。
pause
exit /b 1
