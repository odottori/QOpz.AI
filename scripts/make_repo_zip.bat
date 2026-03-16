@echo off
setlocal EnableExtensions
cd /d %~dp0..

rem Usage: make_repo_zip.bat [REF]  (default: HEAD)
rem Crea un git archive zip del repo. Richiede working tree pulita.

set "REF=%~1"
if "%REF%"=="" set "REF=HEAD"

for /f %%i in ('powershell -NoProfile -Command "Get-Date -Format yyyyMMdd_HHmmss"') do set "TS=%%i"
set "OUTZIP=%~dp0..\QOpz.AI_repo_%TS%.zip"

git rev-parse --is-inside-work-tree >nul 2>&1 || (echo [ERROR] Non e' una repo git. & exit /b 1)

for /f %%s in ('git status --porcelain') do (
  echo [ERROR] Working tree NON pulita. Committa/stasha prima.
  exit /b 1
)

echo [INFO] Archiving ref: %REF%
if exist "%OUTZIP%" del /q "%OUTZIP%"
git archive --format=zip --output "%OUTZIP%" %REF% || (echo [ERROR] git archive fallito. & exit /b 1)
echo [OK] ZIP creato: %OUTZIP%
exit /b 0
