@echo off
setlocal enabledelayedexpansion

set "OPZ_ROOT=%~dp0"
set "OPZ_PY=py"
if exist "%OPZ_ROOT%.venv\Scripts\python.exe" set "OPZ_PY=%OPZ_ROOT%.venv\Scripts\python.exe"

echo OPZ_ENV_SETUP: START
"%OPZ_PY%" tools\opz_env_setup.py
if errorlevel 1 (
  echo OPZ_ENV_SETUP: FAIL rc=%errorlevel%
  exit /b %errorlevel%
)
echo OPZ_ENV_SETUP: OK
echo HINT: run: .\OPZ_ENV_ACTIVATE.bat
exit /b 0
