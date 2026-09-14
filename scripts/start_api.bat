@echo off
setlocal
cd /d %~dp0\..
call scripts\opz_run_api_tab.cmd
exit /b %errorlevel%
