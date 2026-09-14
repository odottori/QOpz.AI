@echo off
setlocal
cd /d %~dp0\..

set "OPZ_ROOT=%cd%\"
set "OPZ_PY=py"
if exist "%OPZ_ROOT%.venv\Scripts\python.exe" set "OPZ_PY=%OPZ_ROOT%.venv\Scripts\python.exe"

set "PORT=8765"
set "HEALTH_URL=http://127.0.0.1:%PORT%/health"
if "%OPZ_AGENT_OWNER%"=="" set "OPZ_AGENT_OWNER=assistant"
if "%OPZ_FORCE_KILL_PORTS%"=="" set "OPZ_FORCE_KILL_PORTS=1"
if "%OPZ_API_START_TIMEOUT_SEC%"=="" set "OPZ_API_START_TIMEOUT_SEC=20"

set "OPZ_API_STDOUT=%OPZ_ROOT%logs\tracked\api.stdout.log"
set "OPZ_API_STDERR=%OPZ_ROOT%logs\tracked\api.stderr.log"
set "OPZ_API_ARGUMENTS=-m uvicorn api.opz_api:app --host 127.0.0.1 --port %PORT%"

echo OPZ_API: checking tracked processes and port %PORT%...
if "%OPZ_FORCE_KILL_PORTS%"=="1" (
  powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0opz_stop_tracked_process.ps1" -Role api >nul 2>nul
)

powershell -NoProfile -ExecutionPolicy Bypass -Command "if((Test-NetConnection -ComputerName 127.0.0.1 -Port %PORT% -WarningAction SilentlyContinue).TcpTestSucceeded){ exit 0 } else { exit 1 }"
if %errorlevel%==0 (
  powershell -NoProfile -ExecutionPolicy Bypass -Command "$ProgressPreference='SilentlyContinue'; try { $r = Invoke-WebRequest -UseBasicParsing -Uri '%HEALTH_URL%' -TimeoutSec 3; if($r.StatusCode -ge 200 -and $r.StatusCode -lt 300){ exit 0 } else { exit 1 } } catch { exit 1 }"
  if %errorlevel%==0 (
    echo OPZ_API: already healthy at %HEALTH_URL%
    exit /b 0
  )
  echo OPZ_API: port %PORT% occupied by non-tracked or unhealthy process - startup blocked.
  echo OPZ_API: no forced kill on untracked processes.
  exit /b 2
)

echo OPZ_API: starting tracked uvicorn on port %PORT%... (python: %OPZ_PY%)
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0opz_start_tracked_process.ps1" -Role api -FilePath "%OPZ_PY%" -ArgumentsLine "%OPZ_API_ARGUMENTS%" -WorkingDirectory "%cd%" -StdoutPath "%OPZ_API_STDOUT%" -StderrPath "%OPZ_API_STDERR%"
set "RC=%errorlevel%"
if not "%RC%"=="0" (
  echo OPZ_API: tracked start failed rc=%RC%
  exit /b %RC%
)

echo OPZ_API: waiting for health %HEALTH_URL% (timeout=%OPZ_API_START_TIMEOUT_SEC%s)...
powershell -NoProfile -ExecutionPolicy Bypass -Command "$ProgressPreference='SilentlyContinue'; $deadline=(Get-Date).AddSeconds(%OPZ_API_START_TIMEOUT_SEC%); while((Get-Date) -lt $deadline){ try { $r = Invoke-WebRequest -UseBasicParsing -Uri '%HEALTH_URL%' -TimeoutSec 3; if($r.StatusCode -ge 200 -and $r.StatusCode -lt 300){ exit 0 } } catch {} Start-Sleep -Milliseconds 500 }; exit 1"
if errorlevel 1 (
  echo OPZ_API: healthcheck timeout at %HEALTH_URL%
  echo OPZ_API: inspect logs %OPZ_API_STDOUT% and %OPZ_API_STDERR%
  "%OPZ_PY%" scripts\opz_process_registry.py list --format line --owner "%OPZ_AGENT_OWNER%"
  exit /b 3
)

echo OPZ_API: healthy at %HEALTH_URL%
"%OPZ_PY%" scripts\opz_process_registry.py list --format line --owner "%OPZ_AGENT_OWNER%"
exit /b 0
