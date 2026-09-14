@echo off
setlocal
set "ROOT=%~dp0"

call "%ROOT%STOP.bat"

echo [CHECK] Verifico porte libere...
netstat -ano | findstr ":8765" | findstr "LISTENING" >nul
if %errorlevel% == 0 (
    echo [ERRORE] Porta 8765 ancora occupata
    exit /b 1
)

netstat -ano | findstr ":8173" | findstr "LISTENING" >nul
if %errorlevel% == 0 (
    echo [ERRORE] Porta 8173 ancora occupata
    exit /b 1
)

echo [START] Lancio QOpz...
start "QOpz-API" cmd /c "cd /d "%ROOT%" && title QOpz-API && "%ROOT%\.venv\Scripts\python.exe" -m uvicorn api.opz_api:app --host 127.0.0.1 --port 8765 --no-use-colors"
start "QOpz-UI" cmd /c "cd /d "%ROOT%ui" && title QOpz-UI && npm run dev -- --host 127.0.0.1 --port 8173"

echo [FINE] Sessione lanciata.
exit /b 0