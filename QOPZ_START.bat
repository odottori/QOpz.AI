@echo off
setlocal EnableExtensions
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\opz_local.ps1" -Action start -Role all
exit /b %errorlevel%
