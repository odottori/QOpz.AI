@echo off
setlocal enabledelayedexpansion

set "OPZ_ROOT=%~dp0"
set "OPZ_PY=py"
if exist "%OPZ_ROOT%.venv\Scripts\python.exe" set "OPZ_PY=%OPZ_ROOT%.venv\Scripts\python.exe"
rem Wrapper: prefer venv python if present.
echo OPZ_F3_T1_RUN: using "%OPZ_PY%"
"%OPZ_PY%" scripts\opz_f3_t1_run.py %*
exit /b %errorlevel%
