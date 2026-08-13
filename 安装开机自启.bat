@echo off
chcp 65001 >nul
cd /d "%~dp0"
where python >nul 2>nul
if %errorlevel%==0 (
  python main.py install
) else (
  echo 未找到 Python。请先安装 Python 3.10 或更高版本，并勾选“Add to PATH”。
)
echo.
pause

