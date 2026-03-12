@echo off
setlocal EnableExtensions

REM Usage: make_repo_zip_local.bat [REPO_DIR] [REF]
REM Defaults: REPO_DIR = current script dir, REF = HEAD

set "REPO_DIR=%~1"
if "%REPO_DIR%"=="" set "REPO_DIR=C:\.dev\QuantOpzioni.AI"

set "REF=%~2"
if "%REF%"=="" set "REF=HEAD"

for /f %%i in ('powershell -NoProfile -Command "Get-Date -Format yyyyMMdd_HHmmss"') do set "TS=%%i"
set "OUTZIP=%~dp0QuantOpzioni.AI_repo_%TS%.zip"

cd /d "%REPO_DIR%" || (echo [ERROR] Repo dir non trovato: %REPO_DIR% & exit /b 1)

git rev-parse --is-inside-work-tree >nul 2>&1 || (echo [ERROR] Non e' una repo git: %REPO_DIR% & exit /b 1)

for /f %%s in ('git status --porcelain') do (
  echo [ERROR] Working tree NON pulita. Committa/stasha prima di zippare.
  exit /b 1
)

echo [INFO] Archiving ref: %REF%
if exist "%OUTZIP%" del /q "%OUTZIP%"

git archive --format=zip --output "%OUTZIP%" %REF% || (echo [ERROR] git archive fallito. & exit /b 1)

echo [OK] ZIP creato: %OUTZIP%
exit /b 0
