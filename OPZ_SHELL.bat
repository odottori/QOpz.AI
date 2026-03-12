@echo off
setlocal

REM OPZ_SHELL.bat
REM Opens a NEW PowerShell window in the project root with venv activated.
REM Uses ExecutionPolicy Bypass for this launched PowerShell only.

set "ROOT=%~dp0"
set "ACT=%ROOT%.venv\Scripts\Activate.ps1"

if not exist "%ROOT%.venv\Scripts\python.exe" (
  echo OPZ_SHELL: .venv not found in "%ROOT%".
  echo Run OPZ_ENV_SETUP.bat first to create it.
  echo.
)

REM Build a PowerShell command that works on Windows PowerShell and PowerShell 7+
set "PSCMD=Set-Location -LiteralPath '%ROOT%'; if (Test-Path -LiteralPath '%ACT%') { . '%ACT%' } else { Write-Host 'OPZ_SHELL: .venv missing - run OPZ_ENV_SETUP.bat' -ForegroundColor Yellow }; Write-Host 'OPZ_SHELL: READY' -ForegroundColor Green; python -c \"import sys; print('PY=', sys.executable)\""

powershell -NoProfile -NoExit -ExecutionPolicy Bypass -Command "%PSCMD%"

endlocal
