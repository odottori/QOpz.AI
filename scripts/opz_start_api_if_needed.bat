@echo off
setlocal
cd /d %~dp0\..

set "OPZ_ROOT=%cd%\"
set "OPZ_PY=py"
if exist "%OPZ_ROOT%.venv\Scripts\python.exe" set "OPZ_PY=%OPZ_ROOT%.venv\Scripts\python.exe"

set "PORT=8765"
if "%OPZ_AGENT_OWNER%"=="" set "OPZ_AGENT_OWNER=assistant"
if "%OPZ_FORCE_KILL_PORTS%"=="" set "OPZ_FORCE_KILL_PORTS=1"

echo OPZ_API: checking tracked processes and port %PORT%...
if "%OPZ_FORCE_KILL_PORTS%"=="1" (
  powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0opz_stop_tracked_process.ps1" -Role api >nul 2>nul
)

powershell -NoProfile -ExecutionPolicy Bypass -Command "if((Test-NetConnection -ComputerName 127.0.0.1 -Port %PORT% -WarningAction SilentlyContinue).TcpTestSucceeded){ exit 0 } else { exit 1 }"
if %errorlevel%==0 (
  echo OPZ_API: port %PORT% occupied by non-tracked process - startup blocked.
  echo OPZ_API: no forced kill on untracked processes.
  exit /b 2
)

echo OPZ_API: starting tracked uvicorn on port %PORT%... (python: %OPZ_PY%)
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0opz_start_tracked_process.ps1" -Role api -FilePath "%OPZ_PY%" -ArgumentList "-m","uvicorn","api.opz_api:app","--reload","--port","%PORT%" -WorkingDirectory "%cd%"
set "RC=%errorlevel%"
if not "%RC%"=="0" (
  echo OPZ_API: tracked start failed rc=%RC%
  exit /b %RC%
)

echo OPZ_API: tracked start requested. listing registry...
"%OPZ_PY%" scripts\opz_process_registry.py list --format line --owner "%OPZ_AGENT_OWNER%"
exit /b 0
