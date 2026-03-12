@echo off
setlocal enabledelayedexpansion

set "OPZ_ROOT=%~dp0"
set "OPZ_PY=py"
if exist "%OPZ_ROOT%.venv\Scripts\python.exe" set "OPZ_PY=%OPZ_ROOT%.venv\Scripts\python.exe"
echo OPZ_FIX_INTEGRITY: START
"%OPZ_PY%" tools\opz_state_normalize.py
if errorlevel 1 exit /b %errorlevel%
"%OPZ_PY%" tools\reconcile_step_index.py
if errorlevel 1 exit /b %errorlevel%
"%OPZ_PY%" tools\rebuild_manifest.py
if errorlevel 1 exit /b %errorlevel%
"%OPZ_PY%" tools\verify_manifest.py
if errorlevel 1 exit /b %errorlevel%
"%OPZ_PY%" tools\certify_steps.py
if errorlevel 1 exit /b %errorlevel%
echo OPZ_FIX_INTEGRITY: OK
exit /b 0
