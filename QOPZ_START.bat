@echo off
setlocal
cd /d %~dp0

set "OPZ_AGENT_OWNER=operator"
if "%OPZ_FORCE_KILL_PORTS%"=="" set "OPZ_FORCE_KILL_PORTS=0"

echo.
echo ============================================================
echo   QOpz.AI ^| tracked startup
echo ============================================================
echo.

call scripts\opz_start_api_if_needed.bat
set "RC_API=%errorlevel%"
if not "%RC_API%"=="0" (
  echo [FAIL] API startup failed rc=%RC_API%
  exit /b %RC_API%
)

call scripts\opz_start_ui_if_needed.bat
set "RC_UI=%errorlevel%"
if not "%RC_UI%"=="0" (
  echo [FAIL] UI startup failed rc=%RC_UI%
  exit /b %RC_UI%
)

echo.
echo [OK] Startup complete.
echo      API health: http://localhost:8765/health
echo      UI:         http://localhost:8173
echo.
exit /b 0
