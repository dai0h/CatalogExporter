@echo off
chcp 65001 >nul
cd /d "%~dp0"
setlocal

set "PYTHON_EXE=C:\Users\daihe\AppData\Local\Programs\Python\Python314\python.exe"

echo 正在验证 v1.3（PySide6）界面层...
echo Python：%PYTHON_EXE%
echo.

if not exist "%PYTHON_EXE%" (
  echo [失败] 未找到 Python 3.14。
  pause
  exit /b 1
)

"%PYTHON_EXE%" -c "import os; os.environ['QT_QPA_PLATFORM']='offscreen'; import tempfile, pathlib; from PySide6.QtWidgets import QApplication; from diskmenu.gui import MainWindow; app=QApplication([]); p=pathlib.Path(tempfile.mkdtemp())/'index.db'; w=MainWindow(str(p)); assert w.authenticated; w._poll_timer.stop(); w._show_timer.stop(); w.conn.close(); print('MainWindow offscreen OK')"
if errorlevel 1 (
  echo [失败] v1.3 界面验证失败。
  pause
  exit /b 1
)

echo.
echo [成功] v1.3 界面层验证通过。
echo.
pause
