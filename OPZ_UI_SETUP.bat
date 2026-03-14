@echo off
setlocal enabledelayedexpansion
cd /d %~dp0

set "OPZ_ROOT=%~dp0"
set "OPZ_PY=py"
if exist "%OPZ_ROOT%.venv\Scripts\python.exe" set "OPZ_PY=%OPZ_ROOT%.venv\Scripts\python.exe"

echo OPZ_UI_SETUP: START (python: %OPZ_PY%)

echo OPZ_UI_SETUP: Python deps (venv)
"%OPZ_PY%" -m pip install -r requirements-web.txt || exit /b 2

echo OPZ_UI_SETUP: Node check
where node >nul 2>nul
if errorlevel 1 (
  echo ERROR: Node.js non trovato. Installa Node LTS e riprova.
  exit /b 3
)
where npm >nul 2>nul
if errorlevel 1 (
  echo ERROR: npm non trovato. Reinstalla Node.js LTS.
  exit /b 3
)

if not exist ui\package.json (
  echo ERROR: ui\package.json missing.
  exit /b 4
)

pushd ui
if not exist node_modules (
  echo OPZ_UI_SETUP: npm install
  npm install || exit /b 5
) else (
  echo OPZ_UI_SETUP: node_modules present (skip npm install)
)
popd

echo OPZ_UI_SETUP: DONE
exit /b 0
