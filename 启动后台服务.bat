@echo off
cd /d "%~dp0"
where pythonw >nul 2>nul
if %errorlevel%==0 (
  start "" pythonw run_tray.pyw
) else (
  start "" python run_tray.pyw
)

