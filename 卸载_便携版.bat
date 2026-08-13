@echo off
chcp 65001 >nul
title 目录导出管家 卸载

echo ========================================
echo  目录导出管家 卸载
echo ========================================
echo.
echo 正在关闭程序并取消开机自启...

taskkill /IM CatalogExporter.exe /F >nul 2>nul
timeout /t 1 /nobreak >nul

if exist "%~dp0CatalogExporter.exe" (
  "%~dp0CatalogExporter.exe" uninstall
)

echo 已取消开机自启。
echo.
set /p DELDATA=是否同时删除本机的索引数据？(输入 Y 删除，直接回车跳过):
if /i "%DELDATA%"=="Y" (
  rd /s /q "%APPDATA%\DiskMenu"
  echo 索引数据已删除。
) else (
  echo 已保留索引数据。
)

echo.
echo 请手动删除本文件夹，完成卸载。
pause
