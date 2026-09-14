@echo off
setlocal
cd /d %~dp0\..
call scripts\opz_run_ui_tab.cmd
exit /b %errorlevel%
