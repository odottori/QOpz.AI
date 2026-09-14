@echo off
echo ====================================
echo QOpz.AI - Premi Ctrl+C per fermare
echo ====================================
echo.

REM Kill eventuali processi vecchi
taskkill /F /IM uvicorn.exe 2>nul
taskkill /F /IM node.exe 2>nul
timeout /t 1 >nul

echo [1] Avvio API...
start "" cmd.exe /k "cd /d C:\.dev\QOpz.AI && .\.venv\Scripts\python.exe -m uvicorn api.opz_api:app --host 127.0.0.1 --port 8765"

timeout /t 2 >nul

echo [2] Avvio UI...
start "" cmd.exe /k "cd /d C:\.dev\QOpz.AI\ui && npm run dev -- --host 127.0.0.1 --port 8173"

echo.
echo ====================================
echo Entrambi avviati.
echo Premi Ctrl+C per chiudere tutto
echo ====================================
echo.

REM Aspetta Ctrl+C
pause >nul

REM Quando premi Ctrl+C, esegue questo:
echo.
echo Chiusura in corso...
taskkill /F /IM uvicorn.exe 2>nul
taskkill /F /IM node.exe 2>nul
echo Fatto.