@echo off
cd /d "%~dp0"
if exist "dist\DesktopDataStudio\DesktopDataStudio.exe" (
  start "" "dist\DesktopDataStudio\DesktopDataStudio.exe"
) else (
  powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0start.ps1"
)
