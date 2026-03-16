@echo off
setlocal enabledelayedexpansion
cd /d %~dp0..

set "OPZ_PY=py"
if exist ".venv\Scripts\python.exe" set "OPZ_PY=.venv\Scripts\python.exe"

echo OPZ_F3_T1_RUN: using "%OPZ_PY%"
"%OPZ_PY%" scripts\opz_f3_t1_run.py %*
exit /b %errorlevel%
