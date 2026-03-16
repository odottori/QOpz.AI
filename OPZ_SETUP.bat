@echo off
setlocal enabledelayedexpansion
cd /d %~dp0

rem ============================================================
rem  QOpz.AI - SETUP (prima installazione / aggiornamento)
rem
rem  Esegui una volta sola (o dopo pull con nuove dipendenze).
rem  Crea .venv, installa requirements Python, npm install UI.
rem ============================================================

set "OPZ_ROOT=%~dp0"

echo.
echo ============================================================
echo   QOpz.AI  ^|  SETUP
echo ============================================================
echo.

rem --- Python disponibile? ---
python --version >nul 2>&1
if errorlevel 1 (
    echo [FAIL] Python non trovato nel PATH. Installa Python 3.11+.
    exit /b 1
)
for /f "tokens=*" %%v in ('python --version 2^>^&1') do echo [ OK ] %%v

rem --- venv + pip (idempotente) ---
echo.
echo [INFO] Configurazione venv e requirements Python...
python tools\opz_env_setup.py
if errorlevel 1 (
    echo [FAIL] Setup Python fallito - vedi errori sopra.
    exit /b 1
)

rem --- verifica venv creato ---
if not exist ".venv\Scripts\python.exe" (
    echo [FAIL] .venv non trovato dopo setup.
    exit /b 1
)
echo [ OK ] .venv pronto.

rem --- npm install UI ---
echo.
echo [INFO] npm install in ui\...
if not exist "ui\package.json" (
    echo [WARN] ui\package.json non trovato - salto npm.
    goto :npm_done
)
cd /d "%OPZ_ROOT%ui"
npm install
if errorlevel 1 (
    echo [FAIL] npm install fallito.
    exit /b 1
)
echo [ OK ] npm install OK.
cd /d "%OPZ_ROOT%"

:npm_done
echo.
echo ============================================================
echo   SETUP COMPLETATO
echo   Prossimo passo:  OPZ_START.bat
echo ============================================================
echo.
exit /b 0
