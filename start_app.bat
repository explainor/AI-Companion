@echo off
chcp 65001 >nul
setlocal

cd /d "%~dp0"

powershell -ExecutionPolicy Bypass -File "%~dp0start_app.ps1"

echo App is starting. You can close this window.
endlocal
