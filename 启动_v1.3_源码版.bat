@echo off
chcp 65001 >nul
cd /d "%~dp0"
setlocal

set "PYTHON_EXE=C:\Users\daihe\AppData\Local\Programs\Python\Python314\python.exe"
set "LOG=%~dp0v1.3_start.log"

echo 目录导出管家 v1.3 源码版启动诊断 > "%LOG%"
echo 时间：%date% %time% >> "%LOG%"
echo 当前目录：%cd% >> "%LOG%"
echo Python：%PYTHON_EXE% >> "%LOG%"
echo. >> "%LOG%"

if not exist "%PYTHON_EXE%" (
  echo [失败] 未找到 Python 3.14：
  echo %PYTHON_EXE%
  echo [失败] 未找到 Python 3.14：%PYTHON_EXE% >> "%LOG%"
  echo.
  echo 日志已写入：%LOG%
  pause
  exit /b 1
)

echo 正在检查 Python / PySide6 ...
"%PYTHON_EXE%" -c "import sys, PySide6; from PySide6 import QtWidgets; print(sys.version); print('PySide6 OK', PySide6.__version__)" >> "%LOG%" 2>&1
if errorlevel 1 (
  echo [失败] PySide6 未安装，请先执行：
  echo   %PYTHON_EXE% -m pip install -r requirements-build.txt
  type "%LOG%"
  pause
  exit /b 1
)

echo 正在使用 v1.3 源码启动目录导出管家（PySide6 界面）...
echo 如果界面没有出现，请把这个日志文件发给我：
echo %LOG%
echo.

"%PYTHON_EXE%" "%~dp0main.py" >> "%LOG%" 2>&1
set "EXIT_CODE=%ERRORLEVEL%"

echo. >> "%LOG%"
echo 程序退出码：%EXIT_CODE% >> "%LOG%"

if not "%EXIT_CODE%"=="0" (
  echo [失败] 程序异常退出，日志如下：
  type "%LOG%"
) else (
  echo 程序已退出，日志如下：
  type "%LOG%"
)

echo.
echo 日志已写入：%LOG%
pause
