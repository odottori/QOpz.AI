@echo off
setlocal enabledelayedexpansion
cd /d %~dp0..

set "OPZ_PY=py"
if exist ".venv\Scripts\python.exe" set "OPZ_PY=.venv\Scripts\python.exe"

echo OPZ_FIX_INTEGRITY: START
"%OPZ_PY%" tools\opz_state_normalize.py   || exit /b %errorlevel%
"%OPZ_PY%" tools\reconcile_step_index.py  || exit /b %errorlevel%
"%OPZ_PY%" tools\rebuild_manifest.py      || exit /b %errorlevel%
"%OPZ_PY%" tools\verify_manifest.py       || exit /b %errorlevel%
"%OPZ_PY%" tools\certify_steps.py         || exit /b %errorlevel%
echo OPZ_FIX_INTEGRITY: OK
exit /b 0
