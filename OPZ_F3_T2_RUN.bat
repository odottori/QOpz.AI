@echo off
setlocal enabledelayedexpansion

set "OPZ_ROOT=%~dp0"
set "OPZ_PY=py"
if exist "%OPZ_ROOT%.venv\Scripts\python.exe" set "OPZ_PY=%OPZ_ROOT%.venv\Scripts\python.exe"
rem Wrapper: prefer venv python if present.
echo OPZ_F3_T2_RUNNER: IMPORT_SMOKE
"%OPZ_PY%" -c "import tools.opz_f3_t2_runner; print('IMPORT_SMOKE OK')"
if errorlevel 1 (
  echo CRITICAL_FAIL: cannot import tools.opz_f3_t2_runner. Run: py -m unittest -q
  exit /b 2
)

echo.
echo CONFIRM REQUIRED: this will PLACE/MODIFY/CANCEL PAPER orders via TWS/IB Gateway.
set /p OPZ_CONFIRM=Type EXACTLY "YES" to continue: 
if /I not "%OPZ_CONFIRM%"=="YES" (
  echo ABORTED
  exit /b 3
)
"%OPZ_PY%" scripts\opz_f3_t2_run.py
exit /b %errorlevel%
