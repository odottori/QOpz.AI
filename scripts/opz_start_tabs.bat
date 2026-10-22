@echo off
setlocal EnableExtensions
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0opz_local.ps1" -Action start -Role all
exit /b %errorlevel%
