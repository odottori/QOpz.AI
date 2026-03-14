@echo off
setlocal enabledelayedexpansion
cd /d %~dp0

set "OPZ_ROOT=%~dp0"
set "OPZ_PY=py"
if exist "%OPZ_ROOT%.venv\Scripts\python.exe" set "OPZ_PY=%OPZ_ROOT%.venv\Scripts\python.exe"

echo OPZ_FREEZE_F3_T1: START (python: %OPZ_PY%)
"%OPZ_PY%" tools\opz_step_ctl.py --freeze F3-T1 --reason "IBKR onboarding pending" --advance-to F6-T1 || exit /b 2

echo OPZ_FREEZE_F3_T1: reconcile + manifest + certify
"%OPZ_PY%" tools\reconcile_step_index.py || exit /b 2
"%OPZ_PY%" tools\rebuild_manifest.py || exit /b 2
"%OPZ_PY%" tools\verify_manifest.py || exit /b 2
"%OPZ_PY%" tools\certify_steps.py || exit /b 2
"%OPZ_PY%" tools\release_status.py --format md

echo OPZ_FREEZE_F3_T1: DONE
exit /b 0
