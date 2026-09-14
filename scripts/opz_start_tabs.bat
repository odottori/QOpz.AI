@echo off
setlocal EnableExtensions
cd /d %~dp0\..

if "%OPZ_AGENT_OWNER%"=="" set "OPZ_AGENT_OWNER=operator"
if "%OPZ_FORCE_KILL_PORTS%"=="" set "OPZ_FORCE_KILL_PORTS=1"
if "%OPZ_START_MODE%"=="" set "OPZ_START_MODE=legacy"

echo.
echo ============================================================
echo   QOpz.AI ^| tabs launcher
echo ============================================================
echo [INFO] Stable bootstrap delegated to opz_start_local.bat.
echo.

call scripts\opz_start_local.bat
set "RC=%errorlevel%"
if not "%RC%"=="0" exit /b %RC%

cmd /c where wt >nul 2>nul
if %errorlevel%==0 (
  wt -w 0 new-tab --title "QOPZ API health" cmd /c "curl.exe -sS http://127.0.0.1:8765/health & echo. & pause"
  wt -w 0 new-tab --title "QOPZ UI" cmd /c "start http://127.0.0.1:8173/ & exit"
)
exit /b 0
