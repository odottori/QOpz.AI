@echo off
setlocal EnableExtensions
cd /d %~dp0\..

if "%OPZ_AGENT_OWNER%"=="" set "OPZ_AGENT_OWNER=operator"
if "%OPZ_FORCE_KILL_PORTS%"=="" set "OPZ_FORCE_KILL_PORTS=1"
if "%OPZ_START_MODE%"=="" set "OPZ_START_MODE=legacy"
if "%OPZ_UI_BUILD_MODE%"=="" set "OPZ_UI_BUILD_MODE=auto"

echo.
echo ============================================================
echo   QOpz.AI ^| local startup
echo ============================================================
echo   owner: %OPZ_AGENT_OWNER%
echo   mode: %OPZ_START_MODE%
echo   ui_build: %OPZ_UI_BUILD_MODE%
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
echo      API health: http://127.0.0.1:8765/health
echo      UI:         http://127.0.0.1:8173/
echo.
exit /b 0
