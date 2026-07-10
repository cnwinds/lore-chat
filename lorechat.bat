@echo off
REM Lore Chat dev server control (UTF-8)
setlocal
chcp 65001 >nul 2>&1
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0lorechat.ps1" %*
exit /b %ERRORLEVEL%
