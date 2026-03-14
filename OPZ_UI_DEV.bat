@echo off
setlocal enabledelayedexpansion
cd /d %~dp0

set "OPZ_ROOT=%~dp0"
set "OPZ_PY=py"
if exist "%OPZ_ROOT%.venv\Scripts\python.exe" set "OPZ_PY=%OPZ_ROOT%.venv\Scripts\python.exe"

echo OPZ_UI_DEV: START (python: %OPZ_PY%)
echo - API: http://localhost:8000
echo - UI:  http://localhost:5173

rem Start FastAPI in a new window using venv python
start "OPZ FastAPI" cmd /k "cd /d %OPZ_ROOT% && "%OPZ_PY%" -m uvicorn api.opz_api:app --reload --port 8000"

rem Start React (Vite) in a new window
start "OPZ React" cmd /k "cd /d %OPZ_ROOT%ui && npm run dev"

echo OPZ_UI_DEV: spawned windows.
exit /b 0
