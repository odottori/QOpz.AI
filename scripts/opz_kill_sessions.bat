@echo off
setlocal EnableExtensions EnableDelayedExpansion
cd /d %~dp0\..

set "OPZ_ROOT=%cd%"
if "%OPZ_AGENT_OWNER%"=="" set "OPZ_AGENT_OWNER=operator"
set "API_PORT=8765"
set "UI_PORT=8173"
set "OPZ_PY=py"
if exist "%OPZ_ROOT%\.venv\Scripts\python.exe" set "OPZ_PY=%OPZ_ROOT%\.venv\Scripts\python.exe"

echo.
echo ============================================================
echo   QOpz.AI ^| kill sessioni precedenti
echo ============================================================
echo.
echo [1/4] stop processi tracked (owner=%OPZ_AGENT_OWNER%)...
powershell -NoProfile -ExecutionPolicy Bypass -File "%OPZ_ROOT%\scripts\opz_stop_tracked_process.ps1" -Role api -Owner "%OPZ_AGENT_OWNER%"
powershell -NoProfile -ExecutionPolicy Bypass -File "%OPZ_ROOT%\scripts\opz_stop_tracked_process.ps1" -Role ui -Owner "%OPZ_AGENT_OWNER%"

echo [2/4] kill processi in ascolto su porte %API_PORT% e %UI_PORT%...
call :kill_port %API_PORT%
call :kill_port %UI_PORT%

echo [3/4] cleanup registro processi...
"%OPZ_PY%" "%OPZ_ROOT%\scripts\opz_process_registry.py" cleanup --owner "%OPZ_AGENT_OWNER%"

echo [4/4] verifica porte...
set "API_BUSY=0"
set "UI_BUSY=0"
powershell -NoProfile -ExecutionPolicy Bypass -Command "if((Test-NetConnection -ComputerName 127.0.0.1 -Port %API_PORT% -WarningAction SilentlyContinue).TcpTestSucceeded){ exit 0 } else { exit 1 }"
if %errorlevel%==0 set "API_BUSY=1"
powershell -NoProfile -ExecutionPolicy Bypass -Command "if((Test-NetConnection -ComputerName 127.0.0.1 -Port %UI_PORT% -WarningAction SilentlyContinue).TcpTestSucceeded){ exit 0 } else { exit 1 }"
if %errorlevel%==0 set "UI_BUSY=1"

if "%API_BUSY%"=="0" if "%UI_BUSY%"=="0" (
  echo [OK] Sessioni precedenti chiuse. Porte libere: %API_PORT%, %UI_PORT%.
  exit /b 0
)

if "%API_BUSY%"=="1" echo [WARN] Porta API %API_PORT% ancora occupata.
if "%UI_BUSY%"=="1" echo [WARN] Porta UI %UI_PORT% ancora occupata.
exit /b 1

:kill_port
set "KPORT=%~1"
for /f "tokens=5" %%P in ('netstat -ano ^| findstr /R /C:":%KPORT% .*LISTENING"') do (
  taskkill /F /PID %%P >nul 2>nul
)
exit /b 0
