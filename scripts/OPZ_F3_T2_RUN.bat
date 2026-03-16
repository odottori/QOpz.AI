@echo off
setlocal enabledelayedexpansion
cd /d %~dp0..

set "OPZ_PY=py"
if exist ".venv\Scripts\python.exe" set "OPZ_PY=.venv\Scripts\python.exe"

echo OPZ_F3_T2_RUN: IMPORT_SMOKE
"%OPZ_PY%" -c "import tools.opz_f3_t2_runner; print('IMPORT_SMOKE OK')"
if errorlevel 1 (
  echo CRITICAL_FAIL: cannot import tools.opz_f3_t2_runner.
  exit /b 2
)

echo.
echo CONFIRM REQUIRED: placera' PAPER orders reali via TWS/IB Gateway.
set /p OPZ_CONFIRM=Digita ESATTAMENTE "YES" per continuare:
if /I not "%OPZ_CONFIRM%"=="YES" (
  echo ABORTED
  exit /b 3
)
"%OPZ_PY%" scripts\opz_f3_t2_run.py
exit /b %errorlevel%
