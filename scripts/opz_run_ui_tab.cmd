@echo off
setlocal
cd /d %~dp0\..\ui

title QOPZ UI

echo [QOPZ UI] starting on 127.0.0.1:8173
npm.cmd run dev -- --host 127.0.0.1 --port 8173
set "RC=%errorlevel%"
echo [QOPZ UI] exited rc=%RC%
exit /b %RC%
