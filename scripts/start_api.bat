@echo off
call C:\.dev\QOpz.AI\scripts\kill_port.bat 8765
cd /d C:\.dev\QOpz.AI
set "OPZ_PY=py"
if exist ".venv\Scripts\python.exe" set "OPZ_PY=.venv\Scripts\python.exe"
"%OPZ_PY%" -m uvicorn api.opz_api:app --reload --port 8765
