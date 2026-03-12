@echo off
setlocal

if not exist ".venv\Scripts\activate.bat" (
  echo OPZ_ENV_ACTIVATE: CRITICAL_FAIL .venv not found. Run OPZ_ENV_SETUP.bat first.
  exit /b 2
)

call ".venv\Scripts\activate.bat"
echo OPZ_ENV_ACTIVATE: OK
echo HINT: python is now: 
where python
