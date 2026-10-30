@echo off
cd /d "%~dp0"
if exist "dist\v0.3.10\DesktopDataStudio\DesktopDataStudio.exe" if exist "dist\v0.3.10\DesktopDataStudio\engines\manifest.json" (
  start "" "dist\v0.3.10\DesktopDataStudio\DesktopDataStudio.exe"
  exit /b
)
if exist "dist\v0.3.9\DesktopDataStudio\DesktopDataStudio.exe" if exist "dist\v0.3.9\DesktopDataStudio\engines\manifest.json" (
  start "" "dist\v0.3.9\DesktopDataStudio\DesktopDataStudio.exe"
  exit /b
)
if exist "dist\v0.3.8\DesktopDataStudio\DesktopDataStudio.exe" if exist "dist\v0.3.8\DesktopDataStudio\engines\manifest.json" (
  start "" "dist\v0.3.8\DesktopDataStudio\DesktopDataStudio.exe"
  exit /b
)
if exist "dist\v0.3.7\DesktopDataStudio\DesktopDataStudio.exe" if exist "dist\v0.3.7\DesktopDataStudio\engines\manifest.json" (
  start "" "dist\v0.3.7\DesktopDataStudio\DesktopDataStudio.exe"
  exit /b
)
if exist "dist\v0.3.6\DesktopDataStudio\DesktopDataStudio.exe" if exist "dist\v0.3.6\DesktopDataStudio\engines\manifest.json" (
  start "" "dist\v0.3.6\DesktopDataStudio\DesktopDataStudio.exe"
  exit /b
)
if exist "dist\v0.3.5\DesktopDataStudio\DesktopDataStudio.exe" if exist "dist\v0.3.5\DesktopDataStudio\engines\manifest.json" (
  start "" "dist\v0.3.5\DesktopDataStudio\DesktopDataStudio.exe"
  exit /b
)
if exist "dist\DesktopDataStudio\DesktopDataStudio.exe" (
  start "" "dist\DesktopDataStudio\DesktopDataStudio.exe"
) else (
  powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0start.ps1"
)
