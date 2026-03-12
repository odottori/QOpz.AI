@echo off
setlocal enabledelayedexpansion

set "OPZ_ROOT=%~dp0"
set "OPZ_PY=py"
if exist "%OPZ_ROOT%.venv\Scripts\python.exe" set "OPZ_PY=%OPZ_ROOT%.venv\Scripts\python.exe"
echo OPZ_REPAIR_F3_T2_STATE: START
"%OPZ_PY%" tools\opz_step_ctl.py --uncomplete F3-T2 --block F3-T2 --reason "Options API not validated; strict mode" --set-next F6-T1
if errorlevel 1 exit /b %errorlevel%
call OPZ_FIX_INTEGRITY.bat
exit /b %errorlevel%
