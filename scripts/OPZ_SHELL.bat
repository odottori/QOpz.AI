@echo off
setlocal

rem Apre una finestra PowerShell con .venv attivato, posizionata alla root del progetto.
set "ROOT=%~dp0.."
set "ACT=%ROOT%\.venv\Scripts\Activate.ps1"

if not exist "%ROOT%\.venv\Scripts\python.exe" (
  echo OPZ_SHELL: .venv non trovato in "%ROOT%".
  echo Eseguire OPZ_SETUP.bat prima.
  echo.
)

set "PSCMD=Set-Location -LiteralPath '%ROOT%'; if (Test-Path -LiteralPath '%ACT%') { . '%ACT%' } else { Write-Host 'OPZ_SHELL: .venv mancante - eseguire OPZ_SETUP.bat' -ForegroundColor Yellow }; Write-Host 'OPZ_SHELL: READY' -ForegroundColor Green; python -c \"import sys; print('PY=', sys.executable)\""

powershell -NoProfile -NoExit -ExecutionPolicy Bypass -Command "%PSCMD%"
endlocal
