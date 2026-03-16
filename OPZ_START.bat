@echo off
setlocal enabledelayedexpansion
cd /d %~dp0

rem ============================================================
rem  QOpz.AI - AVVIO  (uso quotidiano)
rem
rem  PORTE — definite QUI come sorgente di verita'.
rem  Se le cambi, aggiorna ANCHE:
rem    api/opz_api.py      -> CORSMiddleware allow_origins
rem    ui/vite.config.ts   -> server.port
rem    ui/src/App.tsx      -> API_BASE  e  href link /health
rem ============================================================
set "API_PORT=8765"
set "UI_PORT=8173"
set "OPZ_ROOT=%~dp0"

echo.
echo ============================================================
echo   QOpz.AI  ^|  AVVIO
echo   API  :  http://localhost:%API_PORT%
echo   UI   :  http://localhost:%UI_PORT%
echo ============================================================
echo.

rem --- prerequisiti ---
if not exist ".venv\Scripts\python.exe" (
    echo [FAIL] .venv non trovato. Eseguire OPZ_SETUP.bat prima.
    exit /b 1
)
if not exist "ui\node_modules" (
    echo [FAIL] ui\node_modules non trovato. Eseguire OPZ_SETUP.bat prima.
    exit /b 1
)

set "OPZ_PY=%OPZ_ROOT%.venv\Scripts\python.exe"
echo [ OK ] venv: %OPZ_PY%

rem --- libera porte (kill precedenti) ---
echo [INFO] Libero porta API %API_PORT%...
call scripts\kill_port.bat %API_PORT%
echo [INFO] Libero porta UI  %UI_PORT%...
call scripts\kill_port.bat %UI_PORT%

rem --- avvio API in nuova finestra ---
echo [INFO] Avvio API (porta %API_PORT%)...
start "OPZ-API :%API_PORT%" cmd /k "cd /d "%OPZ_ROOT%" && "%OPZ_PY%" -m uvicorn api.opz_api:app --reload --port %API_PORT%"

rem --- avvio UI in nuova finestra ---
echo [INFO] Avvio UI  (porta %UI_PORT%)...
start "OPZ-UI  :%UI_PORT%" cmd /k "cd /d "%OPZ_ROOT%ui" && node_modules\.bin\vite.cmd"

echo.
echo ============================================================
echo   AVVIATO — attendi 3-5 sec per inizializzazione
echo   API health:  http://localhost:%API_PORT%/health
echo   UI:          http://localhost:%UI_PORT%
echo ============================================================
echo.
exit /b 0
