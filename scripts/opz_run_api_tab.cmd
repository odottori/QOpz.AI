@echo off
setlocal
cd /d %~dp0\..

title QOPZ API
set "OPZ_PY=py"
if exist ".venv\Scripts\python.exe" set "OPZ_PY=.venv\Scripts\python.exe"

echo [QOPZ API] starting on 127.0.0.1:8765
echo [QOPZ API] python=%OPZ_PY%
%OPZ_PY% -m uvicorn api.opz_api:app --host 127.0.0.1 --port 8765
set "RC=%errorlevel%"
echo [QOPZ API] exited rc=%RC%
exit /b %RC%
