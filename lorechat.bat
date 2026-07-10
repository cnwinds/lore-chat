@echo off
REM Lore Chat launcher (UTF-8 + PowerShell)
chcp 65001 >nul 2>&1
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\lorechat.ps1" %*
exit /b %ERRORLEVEL%
