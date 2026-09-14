@echo off
setlocal EnableDelayedExpansion
echo [STOP] Pulizia processi QOpz...

taskkill /F /FI "WINDOWTITLE eq QOpz-API*" 2>nul
taskkill /F /FI "WINDOWTITLE eq QOpz-UI*" 2>nul

echo [VERIFICA] Controllo porte...
:check_ports
set "PORTS_BUSY=0"

netstat -ano | findstr ":8765" | findstr "LISTENING" >nul
if %errorlevel% == 0 (
    echo [WAIT] Porta 8765 occupata...
    set "PORTS_BUSY=1"
    for /f "tokens=5" %%a in ('netstat -ano ^| findstr ":8765" ^| findstr "LISTENING"') do (
        taskkill /F /PID %%a 2>nul
    )
)

netstat -ano | findstr ":8173" | findstr "LISTENING" >nul
if %errorlevel% == 0 (
    echo [WAIT] Porta 8173 occupata...
    set "PORTS_BUSY=1"
    for /f "tokens=5" %%a in ('netstat -ano ^| findstr ":8173" ^| findstr "LISTENING"') do (
        taskkill /F /PID %%a 2>nul
    )
)

if %PORTS_BUSY% == 1 (
    timeout /t 1 /nobreak >nul
    goto check_ports
)

echo [OK] Pulizia completata - porte libere.
exit /b 0