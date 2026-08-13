@echo off
chcp 65001 >nul
cd /d "%~dp0"

set "DEST=%LOCALAPPDATA%\CatalogExporterApp"
echo 正在复制程序到 %DEST%
if not exist "%DEST%" mkdir "%DEST%"
robocopy "%~dp0" "%DEST%" /E /XD .git __pycache__ build dist .venv tests /XF *.pyc /NFL /NDL /NJH /NJS
if %errorlevel% GEQ 8 (
  echo 复制失败，请检查权限。
  pause
  exit /b 1
)

cd /d "%DEST%"
where python >nul 2>nul
if errorlevel 1 (
  echo 未找到 Python。请先安装 Python 3.10+ 并勾选 Add to PATH。
  pause
  exit /b 1
)

python main.py install
echo 开机自启已设置。
echo 正在启动后台托盘程序...
if exist "%SystemRoot%\System32\where.exe" (
  where pythonw >nul 2>nul
  if errorlevel 1 (
    start "" python run_tray.pyw
  ) else (
    start "" pythonw run_tray.pyw
  )
) else (
  start "" python run_tray.pyw
)

echo.
echo 安装完成。以后开机会自动在托盘运行；托盘右键可打开主界面。
pause
