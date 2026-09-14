@echo off
setlocal
cd /d %~dp0\..\ui

set "PORT=8173"
set "UI_URL=http://127.0.0.1:%PORT%/"
if "%OPZ_AGENT_OWNER%"=="" set "OPZ_AGENT_OWNER=assistant"
if "%OPZ_FORCE_KILL_PORTS%"=="" set "OPZ_FORCE_KILL_PORTS=1"
if "%OPZ_UI_START_TIMEOUT_SEC%"=="" set "OPZ_UI_START_TIMEOUT_SEC=25"

set "OPZ_ROOT=%~dp0\..\"
set "OPZ_UI_STDOUT=%OPZ_ROOT%logs\tracked\ui.stdout.log"
set "OPZ_UI_STDERR=%OPZ_ROOT%logs\tracked\ui.stderr.log"
set "OPZ_UI_ARGUMENTS=run dev -- --host 127.0.0.1 --port %PORT%"

echo OPZ_UI: checking tracked processes and port %PORT%...
if "%OPZ_FORCE_KILL_PORTS%"=="1" (
  powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0opz_stop_tracked_process.ps1" -Role ui >nul 2>nul
)

powershell -NoProfile -ExecutionPolicy Bypass -Command "if((Test-NetConnection -ComputerName 127.0.0.1 -Port %PORT% -WarningAction SilentlyContinue).TcpTestSucceeded){ exit 0 } else { exit 1 }"
if %errorlevel%==0 (
  powershell -NoProfile -ExecutionPolicy Bypass -Command "$ProgressPreference='SilentlyContinue'; try { $r = Invoke-WebRequest -UseBasicParsing -Uri '%UI_URL%' -TimeoutSec 3; if($r.StatusCode -ge 200 -and $r.StatusCode -lt 400){ exit 0 } else { exit 1 } } catch { exit 1 }"
  if %errorlevel%==0 (
    echo OPZ_UI: already responding at %UI_URL%
    exit /b 0
  )
  echo OPZ_UI: port %PORT% occupied by non-tracked or unhealthy process - startup blocked.
  echo OPZ_UI: no forced kill on untracked processes.
  exit /b 2
)

echo OPZ_UI: starting tracked vite on port %PORT%...
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0opz_start_tracked_process.ps1" -Role ui -FilePath "npm.cmd" -ArgumentsLine "%OPZ_UI_ARGUMENTS%" -WorkingDirectory "%cd%" -StdoutPath "%OPZ_UI_STDOUT%" -StderrPath "%OPZ_UI_STDERR%"
set "RC=%errorlevel%"
if not "%RC%"=="0" (
  echo OPZ_UI: tracked start failed rc=%RC%
  exit /b %RC%
)

echo OPZ_UI: waiting for HTTP %UI_URL% (timeout=%OPZ_UI_START_TIMEOUT_SEC%s)...
powershell -NoProfile -ExecutionPolicy Bypass -Command "$ProgressPreference='SilentlyContinue'; $deadline=(Get-Date).AddSeconds(%OPZ_UI_START_TIMEOUT_SEC%); while((Get-Date) -lt $deadline){ try { $r = Invoke-WebRequest -UseBasicParsing -Uri '%UI_URL%' -TimeoutSec 3; if($r.StatusCode -ge 200 -and $r.StatusCode -lt 400){ exit 0 } } catch {} Start-Sleep -Milliseconds 500 }; exit 1"
if errorlevel 1 (
  echo OPZ_UI: readiness timeout at %UI_URL%
  echo OPZ_UI: inspect logs %OPZ_UI_STDOUT% and %OPZ_UI_STDERR%
  cd /d %~dp0\..
  set "OPZ_PY=py"
  if exist "%cd%\.venv\Scripts\python.exe" set "OPZ_PY=%cd%\.venv\Scripts\python.exe"
  "%OPZ_PY%" scripts\opz_process_registry.py list --format line --owner "%OPZ_AGENT_OWNER%"
  exit /b 3
)

echo OPZ_UI: healthy at %UI_URL%
cd /d %~dp0\..
set "OPZ_PY=py"
if exist "%cd%\.venv\Scripts\python.exe" set "OPZ_PY=%cd%\.venv\Scripts\python.exe"
"%OPZ_PY%" scripts\opz_process_registry.py list --format line --owner "%OPZ_AGENT_OWNER%"
exit /b 0
